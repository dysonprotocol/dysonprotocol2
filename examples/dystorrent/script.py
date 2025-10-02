from dys import _query, get_script_address
import hashlib
import bencoder
import json
from urllib.parse import unquote


# Config: fixed piece length for determinism and bounded CPU
PIECE_LENGTH = 1048576  # 1 MiB


def _normalize_prefix(prefix: str) -> str:
    assert (
        isinstance(prefix, str) and len(prefix) > 0
    ), f"invalid index prefix: {prefix}"
    # URL-decoding is handled in wsgi; keep this as a pure storage prefix
    if not prefix.endswith("/"):
        return prefix + "/"
    return prefix


def _safe_path_segments(relative_path: str):
    # Disallow traversal and empty segments
    assert ".." not in relative_path, f"invalid path segment: {relative_path}"
    parts = relative_path.split("/") if relative_path else []
    filtered = []
    for p in parts:
        if p is None:
            continue
        if p == "" or p == ".":
            continue
        assert "/" not in p and "\\" not in p, f"invalid path: {relative_path}"
        filtered.append(p)
    if len(filtered) == 0:
        return ["index.json"]
    return filtered


def _list_storage_entries(owner: str, prefix: str):
    # Iterate with page-key until exhausted
    entries = []
    page_key = None
    while True:
        pagination = {"reverse": False}
        if page_key is not None:
            pagination["key"] = page_key
        query = {
            "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
            "owner": owner,
            "index_prefix": prefix,
            "pagination": pagination,
        }
        result = _query(query)
        page_entries = result.get("entries", [])
        for e in page_entries:
            entries.append(e)
        page = result.get("pagination", {})
        page_key = page.get("next_key")
        if not page_key:
            break
    return entries


def _build_file_records(owner: str, prefix: str):
    normalized = _normalize_prefix(prefix)
    raw_entries = _list_storage_entries(owner, normalized)
    file_records = []
    for entry in raw_entries:
        full_index = entry.get("index", "")
        assert full_index.startswith(normalized), f"entry outside prefix: {full_index}"
        rel = full_index[len(normalized) :]
        path_segments = _safe_path_segments(rel)
        # entry["data"] is a string; serve UTF-8 bytes
        data_str = entry.get("data", "")
        data_bytes = data_str.encode("utf-8")
        file_records.append(
            {
                "path": path_segments,
                "length": len(data_bytes),
                "bytes": data_bytes,
            }
        )

    # Deterministic order: lexicographic by path joined with '/'
    def _join_path(rec):
        return "/".join(rec["path"]) if rec and rec.get("path") else ""

    file_records.sort(key=_join_path)
    return file_records


def _compute_pieces(file_records):
    # Concatenate file bytes in order and hash in PIECE_LENGTH chunks
    buffer_bytes = b""
    for rec in file_records:
        buffer_bytes += rec["bytes"]
    pieces = b""
    offset = 0
    total_len = len(buffer_bytes)
    while offset < total_len:
        end = offset + PIECE_LENGTH
        if end > total_len:
            end = total_len
        chunk = buffer_bytes[offset:end]
        digest = hashlib.sha1(chunk).digest()
        pieces += digest
        offset = end
    return pieces


def gen_torrent(index: str, webseed_base_url=None):
    owner = get_script_address()
    prefix = _normalize_prefix(index)
    file_records = _build_file_records(owner, prefix)

    # Fallback to single-file torrent if exact index exists and prefix has no entries
    is_single = False
    if len(file_records) == 0:
        single_query = {
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": owner,
            "index": index,
        }
        single_res = _query(single_query)
        if isinstance(single_res, dict) and ("entry" in single_res):
            data_str = single_res["entry"].get("data", "")
            data_bytes = data_str.encode("utf-8")
            name_parts = [p for p in index.split("/") if p != ""]
            single_name = name_parts[-1] if len(name_parts) > 0 else "index.json"
            file_records = [
                {"path": [single_name], "length": len(data_bytes), "bytes": data_bytes}
            ]
            is_single = True

    # If still empty, signal caller to 404
    if len(file_records) == 0:
        return None

    pieces = _compute_pieces(file_records)
    info = {"piece length": PIECE_LENGTH, "private": 0, "pieces": pieces}
    if is_single:
        rec0 = file_records[0]
        info["length"] = rec0["length"]
        info["name"] = rec0["path"][0]
    else:
        files = []
        for rec in file_records:
            files.append({"length": rec["length"], "path": rec["path"]})
        info_name_raw = prefix.strip("/") or "dataset"
        info_name = (
            "_".join([p for p in info_name_raw.split("/") if p != ""]) or "dataset"
        )
        info["name"] = info_name
        info["files"] = files

    # WebSeed absolute URL if provided, else relative
    webseed_path = "/seed/" + prefix
    webseed = webseed_base_url if webseed_base_url else webseed_path
    torrent = {
        "announce": "",
        "info": info,
        "url-list": [webseed],
        "httpseeds": [webseed],
        "comment": json.dumps({"index": prefix, "owner": owner}),
    }
    return bencoder.encode(torrent)


def _serve_bytes(start_response, body_bytes, content_type="application/octet-stream"):
    status = "200 OK"
    headers = [("Content-Type", content_type), ("Content-Length", str(len(body_bytes)))]
    start_response(status, headers)
    return [body_bytes]


def _not_found(start_response, message):
    body = message.encode("utf-8")
    start_response(
        "404 Not Found",
        [("Content-Type", "text/plain"), ("Content-Length", str(len(body)))],
    )
    return [body]


def _get_entry_bytes(owner: str, index: str):
    # Use List to avoid raising exceptions on not found
    query = {
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": owner,
        "index_prefix": index,
        "pagination": {"limit": 10},
    }
    result = _query(query)
    entries = result.get("entries", [])
    for e in entries:
        if e.get("index", "") == index:
            return e.get("data", "").encode("utf-8")
    return None


def _build_webseed_base(environ, prefix: str):
    # Prefer forwarded proto/host if present (behind proxy)
    scheme = environ.get("HTTP_X_FORWARDED_PROTO", "")
    if scheme == "":
        scheme = environ.get("wsgi.url_scheme", "http")
    host = environ.get("HTTP_X_FORWARDED_HOST", "")
    if host == "":
        host = environ.get("HTTP_HOST", "")
    if host == "":
        host = environ.get("HTTP_X_FORWARDED_HOST", "")
    # Multiple hosts -> first
    if "," in host:
        host = host.split(",")[0]
    # Trim any trailing colon
    host = host.rstrip(":")
    base_prefix = _normalize_prefix(prefix)
    return scheme + "://" + host + "/seed/" + base_prefix


def wsgi(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET")
    assert method in ["GET"], f"unsupported method: {method}"
    path_info = environ.get("PATH_INFO", "")
    if path_info.startswith("/torrent/"):
        # Path after /torrent/ is the storage prefix (URL-decoded)
        raw = path_info[len("/torrent/") :]
        safe_index = unquote(raw)
        # Build absolute webseed base URL from WSGI env
        webseed_base = _build_webseed_base(environ, safe_index)
        torrent_bytes = gen_torrent(safe_index, webseed_base_url=webseed_base)
        if torrent_bytes is None:
            return _not_found(start_response, "no entries for index")
        status = "200 OK"
        name_raw = safe_index.strip("/") or "dataset"
        name = (
            "_".join([p for p in name_raw.split("/") if p != ""]) or "dataset"
        ) + ".torrent"
        headers = [
            ("Content-Type", "application/x-bittorrent"),
            ("Content-Length", str(len(torrent_bytes))),
            ("Content-Disposition", f'attachment; filename="{name}"'),
        ]
        start_response(status, headers)
        return [torrent_bytes]
    if path_info.startswith("/seed/"):
        # Everything after /seed/ is the full storage index (URL-decoded)
        raw = path_info[len("/seed/") :]
        full_index = unquote(raw)
        owner = get_script_address()
        # Try exact index first, then fallback to parent index (for single-file webseed behavior)
        data_bytes = _get_entry_bytes(owner, full_index)
        if data_bytes is None and "/" in full_index:
            parent_index = full_index.rsplit("/", 1)[0]
            data_bytes = _get_entry_bytes(owner, parent_index)
        if data_bytes is None:
            return _not_found(start_response, f"not found: {full_index}")
        # Handle simple Range: bytes=start-end
        rng = environ.get("HTTP_RANGE", "")
        if rng.startswith("bytes=") and "-" in rng:
            spec = rng.split("=", 1)[1]
            if "," not in spec:
                parts = spec.split("-", 1)
                start_s = parts[0]
                end_s = parts[1]
                if start_s.isdigit() and end_s.isdigit():
                    total = len(data_bytes)
                    start = int(start_s)
                    end = int(end_s)
                    if start <= end and end < total:
                        partial = data_bytes[start : end + 1]
                        headers = [
                            ("Content-Type", "application/octet-stream"),
                            ("Content-Length", str(len(partial))),
                            ("Accept-Ranges", "bytes"),
                            ("Content-Range", f"bytes {start}-{end}/{total}"),
                        ]
                        start_response("206 Partial Content", headers)
                        return [partial]
        return _serve_bytes(start_response, data_bytes, "application/octet-stream")
    return _not_found(start_response, "route not found")
