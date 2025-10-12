from dys import (
    _query,
    _msg,
    get_script_address,
    get_executor_address,
    get_block_info,
    get_attached_messages,
    DysQueryException,
    get_script_version,
    get_script_name,
)
from datetime import datetime
from decimal import Decimal
import math
import json
import typing
import html
from string import Template
from urllib.parse import parse_qsl
import mimetypes
import re
import hashlib
from typing import Callable, Iterable, List, Tuple


############################
# Permissions (principal-scoped: name_or_address)
############################

# Permission vocabulary (granular)
_DEFAULT_ROLE_PERMS = {
    "admin": {
        "roles.manage",
        "roles.assign",
        "roles.revoke",
        "invites.issue",
        "invites.revoke",
    },
    "unary electron": {
        "rate.any",
    },
    "super space pollen": {
        "post.create",
        "post.reference",
    },
    "hyper larva of knowlage": {
        "tag.add.own.existing",
    },
    "cosmic neuron of understnding": {
        "invites.issue",
    },
    "holographic hive mind": {
        "tag.add.any.existing",
        "tag.add.any.new",
    },
}


def resolve_address(name_or_address: str) -> str:
    """Resolve a name or address to a canonical address."""
    resp = _query(
        {
            "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
            "name_or_address": name_or_address,
        }
    )
    address = resp.get("address")
    assert address, f"Unable to resolve principal: {name_or_address}"
    return address


def _role_key(role: str) -> str:
    return f"perm/role/{role}"


def _principal_roles_key(principal: str) -> str:
    return f"perm/principal_roles/{principal}"


def _invite_ssp_key(principal: str) -> str:
    return f"perm/invite/super_space_pollen/{principal}"


def _granted_at_key(role: str, principal: str) -> str:
    return f"perm/granted_at/{role}/{principal}"


def _load_role_perms(role: str) -> set:
    try:
        stored = _get_data(_role_key(role))
    except Exception as _e:
        print(f"load_role_perms missing for {role}: {_e}")
        stored = {}
    perms = set(stored.get("perms", []))
    perms |= _DEFAULT_ROLE_PERMS.get(role, set())
    return perms


def get_roles(principal: str) -> List[str]:
    try:
        data = _get_data(_principal_roles_key(principal))
    except Exception as _e:
        print(f"roles not found for {principal}: {_e}")
        data = {}
    roles = data.get("roles", [])
    # normalize order for determinism
    return sorted(list(set(roles)))


def _has_role(role: str, principal: str) -> bool:
    return role in set(get_roles(principal))


def _has_perm(perm: str, principal: str) -> bool:
    perms: set = set()
    for role in get_roles(principal):
        perms |= _load_role_perms(role)
    return perm in perms


def _add_role(role: str, principal: str) -> None:
    caller = get_executor_address()
    assert _has_perm("roles.assign", caller) or _has_role(
        "admin", caller
    ), "roles.addr.assign required"
    roles = set(get_roles(principal))
    if role in roles:
        return
    roles.add(role)
    _store_data(_principal_roles_key(principal), {"roles": sorted(roles)})


def _remove_role(role: str, principal: str) -> None:
    caller = get_executor_address()
    assert _has_perm("roles.revoke", caller) or _has_role(
        "admin", caller
    ), "roles.addr.revoke required"
    roles = set(get_roles(principal))
    if role not in roles:
        return
    roles.remove(role)
    _store_data(_principal_roles_key(principal), {"roles": sorted(roles)})


def invite(principal: str) -> None:
    caller = get_executor_address()
    assert _has_perm("invites.issue", caller) or _has_role(
        "admin", caller
    ), "invites.issue required"
    ts = int(datetime.now().timestamp())
    _store_data(_invite_ssp_key(principal), {"inviter": caller, "timestamp": ts})


def uninvite(principal: str) -> None:
    caller = get_executor_address()
    assert _has_perm("invites.revoke", caller) or _has_role(
        "admin", caller
    ), "invites.revoke required"
    # reuse existing delete helper
    _delete_data(_invite_ssp_key(principal))


def granted_at(role: str, principal: str):
    try:
        data = _get_data(_granted_at_key(role, principal))
    except Exception as _e:
        print(f"granted_at missing for {role}:{principal}: {_e}")
        data = {}
    return data.get("timestamp")


def bootstrap_permissions() -> None:
    """Persist default role→permission schema; assign admin to script address if desired."""
    # Persist role schemas
    for role, perms in _DEFAULT_ROLE_PERMS.items():
        _store_data(_role_key(role), {"perms": sorted(list(perms))})


def claim(role: str, principal: str) -> None:
    role = str(role).strip()
    address = resolve_address(principal)
    # Claims are self‑service only
    assert (
        address == get_executor_address()
    ), "claim must be executed by the claimed principal"

    now = int(datetime.now().timestamp())

    if role == "super space pollen":
        try:
            invite_rec = _get_data(_invite_ssp_key(principal))
        except Exception as _e:
            print(f"invite not found: {_e}")
            invite_rec = None
        assert invite_rec is not None, "invite not found"
        _add_role("super space pollen", principal)
        _store_data(
            _granted_at_key("super space pollen", principal), {"timestamp": now}
        )
        return

    if role == "hyper larva of knowlage":
        super_ts = granted_at("super space pollen", principal)
        assert super_ts is not None, "super space pollen not yet claimed"
        assert (
            now - int(super_ts) >= 30 * 24 * 60 * 60
        ), "30 days required after super space pollen"
        _add_role("hyper larva of knowlage", principal)
        _store_data(
            _granted_at_key("hyper larva of knowlage", principal), {"timestamp": now}
        )
        return

    if role == "cosmic neuron of understnding":
        super_ts = granted_at("super space pollen", principal)
        assert super_ts is not None, "super space pollen not yet claimed"
        assert (
            now - int(super_ts) >= 60 * 24 * 60 * 60
        ), "60 days required after super space pollen"
        _add_role("cosmic neuron of understnding", principal)
        _store_data(
            _granted_at_key("cosmic neuron of understnding", principal),
            {"timestamp": now},
        )
        return

    raise ValueError(f"unsupported role claim: {role}")


def get_base_domain():
    """Get BASE_DOMAIN from storage settings, with fallback for development."""
    try:
        settings_response = _query(
            {
                "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
                "owner": get_script_address(),
                "index": "settings",
            }
        )
        if "entry" in settings_response and "data" in settings_response["entry"]:
            settings = json.loads(settings_response["entry"]["data"])
            return settings.get("BASE_DOMAIN", "http://localhost:1317")
    except (KeyError, json.JSONDecodeError, TypeError) as e:
        print(f"Failed to load BASE_DOMAIN from settings: {e}")
    # Fallback for development/testing
    return "http://localhost:1317"


WHITELABEL = False
name = get_script_name()
if name and name != "nuance.dys":
    WHITELABEL = True


try:
    import re2 as re  # Only re2 is available onchain
except ImportError as e:
    print(f"re2 not available, falling back to re: {e}")
    import re


# Typing to specify that TEXTAREA is a formatted string, used for content submission
TEXTAREA = typing.Annotated[str, '{"format":"textarea"}']

# Regex to idetify an embedded post as /post_id on it's own line
POST_RE = r"(?:^\n*?|\n+?)/(\d+)(#[^\s]+)?(?:\n*?$|\n+?)"

# The soonest a post rewards can be claimed again for a specific tag
CLAIM_WAIT_SEC = 60 * 60 * 24  # 24hrs


class SafeString(str):
    pass


def get_coins_sent():
    """Parse coins from attached messages (v2 API replacement for old get_coins_sent)."""
    attached_messages = get_attached_messages()
    coins = []

    for msg in attached_messages:
        if msg.get("@type") == "/cosmos.bank.v1beta1.MsgSend":
            # Extract coins from MsgSend message
            msg_coins = msg.get("amount", [])
            for coin in msg_coins:
                coins.append({"denom": coin["denom"], "amount": coin["amount"]})

    return coins


def get_caller():
    """Alias for get_executor_address() for backward compatibility."""
    return get_executor_address()


def publish_post(content: TEXTAREA, author: str = ""):
    """Publish a post to the blockchain.

    Allows the submission of a post to the blockchain.
    If the post includes replies to other posts, those replies are also stored.

    Args:
        content (TEXTAREA): The content of the post.
        author (str): The `.dys` name of the author.

    Returns:
        int: The ID of the published post.
    """

    # Permissions: require the caller to have post.create
    assert _has_perm(
        "post.create", get_executor_address()
    ), "post.create permission required"

    author = author.strip()
    if get_caller() and author:
        # query the blockchain to retrieve the owner of the provided name
        name_resp = _query(
            {
                "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
                "name_or_address": author,
            }
        )
        destination_address = name_resp["address"]
        assert (
            get_caller() == destination_address
        ), f'[{get_caller()}] is not authorized for "{author}" (destination: {destination_address})'

    # set the author to either the name or the caller or test name for preview
    author = author or get_caller()
    post_id = _get_next_id("posts")  # fetch the next available post id

    # find all replies to other posts in the content using regular expression
    replies_to = {}
    replied_to_posts = re.findall(POST_RE, content)
    if len(replied_to_posts) > 5:
        raise ValueError(
            f"Too many replies, max 5 allowed, you have {len(replied_to_posts)}"
        )
    for replied_to_post_id, anchor_text in replied_to_posts:
        reply = replies_to.get(
            replied_to_post_id,
            {
                "from_post": int(post_id),
                "to_post": int(replied_to_post_id),
                "anchors": [],
            },
        )

        if anchor_text:
            reply["anchors"].append(anchor_text)
        replies_to[replied_to_post_id] = reply

    for k, v in replies_to.items():
        _rate(
            "replies",
            _format_id(v["to_post"]),
            v["from_post"],
            "up",
            1,
            metadata={"anchors": v["anchors"]},
        )

    # create a dictionary with post data
    block_info = get_block_info()
    post_data = {
        "post_id": post_id,
        "author": author,
        "content": content,
        "created_height": block_info["height"],
        "created_time": block_info["time"],
    }

    # store the post data and author-post relationship on the blockchain
    _store_data(_get_post_index(post_id), post_data)
    _store_data(_get_author_post_index(**post_data), {"post_id": post_id})

    # _store_data(_get_reply_rewards_index(post_id), {"available": {}, "claimed": {}})
    return post_id  # return the post id


def append_to_post(post_id: int, content: TEXTAREA):
    post = _get_data(_get_post_index(post_id))  # retrieve the post data
    author = post["author"]

    # ensure that only the post author or the owner of the author's name can delete the post
    if author != get_caller():
        try:
            name_resp = _query(
                {
                    "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
                    "name_or_address": author,
                }
            )
            destination_address = name_resp["address"]
            assert get_caller() == destination_address
        except Exception as e:
            raise Exception(
                f'[{get_caller()}] is not the owner or destination of the author "{author}": {e}'
            )

    post["content"] += content
    block_info = get_block_info()
    post["updated_height"] = block_info["height"]
    post["updated_time"] = str(datetime.now())
    _store_data(_get_post_index(post_id), post)


def edit_author_profile(content: TEXTAREA, author: str = ""):

    author = author.strip()
    if get_caller() and author:
        # query the blockchain to retrieve the owner of the provided name
        try:
            name_resp = _query(
                {
                    "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
                    "name_or_address": author,
                }
            )
            destination_address = name_resp["address"]
            assert get_caller() == destination_address
        except Exception as e:
            raise Exception(f'[{get_caller()}] is not authorized for "{author}": {e}')

    # set the author to either the name or the caller
    author = author or get_caller()

    profile_data = _get_profile(author)
    profile_data["content"] = content
    _store_data(_get_author_profile_index(author), profile_data)


def link_page(path: str, post_id: int, author: str, title: str = ""):
    """Link a custom page to a post for an author.

    Creates a custom author page that displays the specified post at the given path.
    Only the author or authorized name owner can create links.

    Args:
        path (str): The custom path for the page (e.g., "about", "contact")
        post_id (int): The ID of the post to display at this path
        author (str): The author name or address
        title (str): The title of the page (optional)
    Raises:
        Exception: If caller is not authorized for the author
        AssertionError: If post doesn't exist or path is invalid
    """
    path = path.strip().strip("/")
    author = author.strip()

    # Validate path
    assert path and len(path) <= 50, "Path must be 1-50 characters"
    # Check if path contains only allowed characters (letters, numbers, hyphens, underscores)
    allowed_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    for c in path:
        assert (
            c in allowed_chars
        ), "Path must contain only letters, numbers, hyphens, and underscores"

    # Validate author is non-falsey and resolves to caller
    assert author, "Author must be provided and non-empty"

    try:
        name_resp = _query(
            {
                "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
                "name_or_address": author,
            }
        )
        destination_address = name_resp["address"]
        assert (
            get_caller() == destination_address
        ), f'Author "{author}" does not resolve to caller address'
    except Exception as e:
        raise Exception(f'[{get_caller()}] is not authorized for "{author}": {e}')

    # Validate post exists
    try:
        _get_data(_get_post_index(post_id))
    except Exception as e:
        raise AssertionError(f"Post {post_id} not found: {e}")

    # Store the page link
    page_data = {
        "post_id": post_id,
        "author": author,
        "title": title,
        "path": path,
        "created_time": get_block_info()["time"],
    }

    _store_data(_get_author_page_index(author, path), page_data)


def unlink_page(path: str, author: str = ""):
    """Remove a custom page link for an author.

    Removes the custom author page at the specified path.
    Only the author or authorized name owner can remove links.

    Args:
        path (str): The custom path to remove
        author (str): The author name or address (defaults to caller)

    Raises:
        Exception: If caller is not authorized for the author
        AssertionError: If page doesn't exist
    """
    path = path.strip()
    author = author.strip()

    # Validate author authorization
    if get_caller() and author:
        try:
            name_resp = _query(
                {
                    "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
                    "name_or_address": author,
                }
            )
            destination_address = name_resp["address"]
            assert get_caller() == destination_address
        except Exception as e:
            raise Exception(f'[{get_caller()}] is not authorized for "{author}": {e}')

    # Set author to caller if not specified
    author = author or get_caller()

    # Delete the page link
    page_index = _get_author_page_index(author, path)

    # Verify page exists before deletion
    try:
        _get_data(page_index)
    except Exception as e:
        raise AssertionError(f"Page '{path}' not found for author '{author}': {e}")

    _delete_data(page_index)


def _get_next_id(key: str):
    index = _get_next_id_index(key)
    # Query the blockchain for the current ID and increment it
    try:
        res = _query(
            {
                "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
                "owner": get_script_address(),
                "index": index,
            }
        )
        next_id = int(json.loads(res["entry"]["data"])) if res.get("entry") else 1
    except Exception as e:
        print(f"Failed to get next ID, defaulting to 1: {e}")
        next_id = 1
    _store_data(index, next_id + 1)  # Store the updated ID back on the blockchain
    return next_id


def _store_data(index: str, data):
    _msg(
        {
            "@type": "/dysonprotocol.storage.v1.MsgStorageSet",
            "owner": get_script_address(),
            "index": index,
            "data": json.dumps(data),  # Data is stored in JSON format
        }
    )


def _get_data(index: str):
    result = _query(
        {
            "@type": "/dysonprotocol.storage.v1.QueryStorageGetRequest",
            "owner": get_script_address(),
            "index": index,
        }
    )
    if not result.get("entry"):
        raise AssertionError(
            f"Error retrieving data: entry not found for index {index}"
        )
    return json.loads(result["entry"]["data"])  # Return the parsed JSON data


def _list_data(prefix: str, **kwargs):
    query_params = {
        "@type": "/dysonprotocol.storage.v1.QueryStorageListRequest",
        "owner": get_script_address(),
        "index_prefix": prefix,
        **kwargs,
    }

    # DEBUG: Print the exact query being constructed
    print(
        f"DEBUG _list_data: Constructing query with params: {json.dumps(query_params, indent=2)}"
    )

    result = _query(query_params)

    # DEBUG: Print the raw result
    print(f"DEBUG _list_data: Raw query result: {json.dumps(result, indent=2)}")

    processed_entries = [
        {"_index": item["index"], **json.loads(item["data"])}
        for item in result.get("entries", [])
    ]

    # DEBUG: Print processed entries
    # print(f"DEBUG _list_data: Processed {len(processed_entries)} entries")
    # for i, entry in enumerate(processed_entries):
    #    print(f"DEBUG _list_data: entry[{i}] = {entry}")

    return (
        processed_entries,
        result.get("pagination", {}),
    )


def _delete_data(index: str):
    _msg(
        {
            "@type": "/dysonprotocol.storage.v1.MsgStorageDelete",
            "owner": get_script_address(),
            "indexes": [index],
        }
    )


def _best_rating(up, down) -> float:
    """Calculate Wilson score with a given confidence level."""

    n = up + down
    if n == 0:
        return 0.0  # No rates, return default score

    z = 1.96  # Z-score for 95% confidence
    p = up / n
    z2 = z**2

    # Wilson score lower bound
    score = (
        p + (z2 / (2 * n)) - z * math.sqrt((p * (1 - p) / n) + (z2 / (4 * n**2)))
    ) / (1 + (z2 / n))

    return round(score, 5)


NEWNESS_BOOST = 2


def _hot_rating(up, down, created_timestamp):

    s = up - down
    order = math.log1p(abs(s))
    sign = (s > 0) - (s < 0)

    time_units = (created_timestamp - 1731932970) / (24 * 60 * 60 * NEWNESS_BOOST)

    return round((sign * order) + time_units, 5)


## Utility functions for generating indexes
def _format_id(id: int) -> str:
    return f"{int(id):015}"


def _get_post_index(post_id: int) -> str:
    return f"posts/{_format_id(post_id)}"


def _get_author_post_prefix(author: str, **kwargs) -> str:
    return f"authors/{author}/posts/"


def _get_author_post_index(author: str, post_id: int, **kwargs) -> str:
    return _get_author_post_prefix(author) + _format_id(post_id)


def _get_author_profile_index(author: str) -> str:
    return f"authors/{author}/profile"


def _get_author_page_index(author: str, path: str) -> str:
    return f"author_page/{author}/{path}"


def _get_author_page_prefix(author: str) -> str:
    return f"author_page/{author}/"


def _get_next_id_index(key: str) -> str:
    return f"next_id/{key}"


################
###  Rating  ###
################


def validate_tag_name(tag_name: str) -> bool:
    """Validate a tag name to ensure it is a single word containing only letters, numbers, and hyphens."""
    return re.match(r"^[a-zA-Z0-9-]+$", tag_name) is not None


def rate_tag(
    tag_name: str,
    post_id: int,
    rate: typing.Literal["up", "down"],
    contributor: str = "",
):

    assert len(tag_name) <= 64, f"Tag is too long (max 64): {len(tag_name)}"
    coins = get_coins_sent()
    assert (
        len(coins) == 1 and coins[0]["denom"] == "udys"
    ), f"Invalid coins, must send udys and only udys, sent: {coins}"
    coins[0]["amount"] = int(coins[0]["amount"])
    amount = coins[0]["amount"]
    rate_amount = amount / 1000000
    # Permissions gating for tag creation vs adding existing tags
    caller_addr = get_executor_address()

    def _tag_exists_globally(tag: str) -> bool:
        try:
            prefix = _get_rating_rate_prefix("tags", tag, "best")
            entries, _ = _list_data(prefix, pagination={"limit": 1})
            return len(entries) > 0
        except Exception as _e:
            print(f"tag_exists check failed: {_e}")
            return False

    exists_globally = _tag_exists_globally(tag_name)
    if not exists_globally:
        # creating a new tag anywhere requires tag.add.any.new
        assert _has_perm(
            "tag.add.any.new", caller_addr
        ), "tag.add.any.new permission required to create new tags"
    else:
        if not _has_perm("tag.add.any.existing", caller_addr):
            # if not global-any, allow only own existing tag add with tag.add.own.existing
            post = _get_data(_get_post_index(post_id))
            author = post["author"]
            if author != get_caller():
                name_resp = _query(
                    {
                        "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
                        "name_or_address": author,
                    }
                )
                destination_address = name_resp["address"]
                assert (
                    get_caller() == destination_address
                ), f"Only the author may add existing tags to own post"
            assert _has_perm(
                "tag.add.own.existing", caller_addr
            ), "tag.add.own.existing permission required"

    try:
        rate_index = _get_rate_index("tags", tag_name, post_id)
        _get_data(rate_index)
    except Exception as e:
        # Post Tag doesn't exist on this post; existing author checks retained
        print(f"Rate index not found: {e}")
        post = _get_data(_get_post_index(post_id))

        author = post["author"]
        # ensure that only the post author or the owner of the author's name can tag the post
        if author != get_caller():
            name_resp = _query(
                {
                    "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
                    "name_or_address": author,
                }
            )
            destination_address = name_resp["address"]
            assert (
                get_caller() == destination_address
            ), f"Nonexistant tag[{tag_name}] for post_id[{post_id}] and only the author[{post['author']}] can add new tags not you[{get_caller()}]"
    _rate("tags", tag_name, post_id, rate, rate_amount, contributor=contributor)


def rate_reply(post_id: int, reply_post_id: int, rate: str):

    reply_post_id = int(reply_post_id)
    post_id = int(post_id)
    coins = get_coins_sent()
    assert (
        len(coins) == 1 and coins[0]["denom"] == "udys"
    ), f"Invalid coins, must send udys and only udys, sent: {coins}"
    coins[0]["amount"] = int(coins[0]["amount"])
    amount = coins[0]["amount"]
    rate_amount = amount / 1000000

    # Check if the reply relationship exists by looking for the reply in the hot list
    try:
        prefix = _get_rating_rate_prefix("replies", _format_id(post_id), "hot")
        hot_replies, _ = _list_data(prefix)
        reply_exists = any([reply["id"] == reply_post_id for reply in hot_replies])
        assert (
            reply_exists
        ), f"Reply post {reply_post_id} not found in replies to post {post_id}"
    except Exception as e:
        raise Exception(
            f"Nonexistant reply for post_id[{post_id}] and reply post_id[{reply_post_id}]: {e}"
        )

    _rate("replies", _format_id(post_id), reply_post_id, rate, rate_amount)


def _rate(
    namespace: str,
    tag_name: str,
    id: int,
    rate: str,
    amount: int = 1,
    metadata=None,
    contributor: str = "",
):
    """Rate on a tag within a namespace and update the score, including reverse indexing.

    Args:
        namespace (str): The namespace within which the tag resides.
        tag_name (str): The tag to rate on.
        id (int): The identifier for the item being rated on.
        rate (str): 'up' for uprate, 'down' for downrate.
        amount (int): The amount to increment the rate by (default is 1).

    Raises:
        ValueError: If rate is not 'up' or 'down'.
    """

    assert amount > 0, "Amount must be greater than 0"
    assert validate_tag_name(tag_name), "Tag must be alphanumeric"

    rate_index = _get_rate_index(namespace, tag_name, id)

    coins = get_coins_sent()
    # Fetch existing rate data or create a new entry
    try:
        rate_data = _get_data(rate_index)
    except Exception as e:
        print(f"Creating new rate data: {e}")
        block_info = get_block_info()
        rate_data = {
            "namespace": namespace,
            "tag_name": tag_name,
            "id": id,
            "up": 0,
            "down": 0,
            "best_rating": 0,
            "hot_rating": 0,
            "created_height": block_info["height"],
            "created_timestamp": int(datetime.now().timestamp()),
            "metadata": {},
        }

    # Remove old score and reverse indexes
    _delete_rating_index(rate_data)
    _delete_reverse_rating_index(rate_data)

    if metadata:
        rate_data["metadata"] = metadata

    # Update rate counts
    if rate == "up":
        rate_data["up"] += amount
    elif rate == "down":
        rate_data["down"] += amount
    else:
        raise ValueError("Rate must be 'up' or 'down'.")

    # Recalculate scores
    rate_data["best_rating"] = _best_rating(rate_data["up"], rate_data["down"])
    rate_data["hot_rating"] = _hot_rating(
        rate_data["up"], rate_data["down"], rate_data["created_timestamp"]
    )

    # Store updated rate data and update indexes
    _store_data(rate_index, rate_data)
    _set_rating_index(rate_data)
    _set_reverse_rating_index(rate_data)
    _add_rewards(tag_name, coins, namespace=namespace, contributor=contributor)


def _track_contributor_rewards(namespace, tag_name, coins, contributor):
    # get the current index
    index = _get_tag_contributor_index(namespace, tag_name, contributor)
    try:
        data = _get_data(index)
    except Exception as e:
        print(f"Contributor data not found, creating new: {e}")
        data = {}

    # delete old reverse index
    for denom, amount in data.items():
        try:
            _delete_data(
                _get_reverse_contributor_index(
                    namespace, tag_name, denom, amount, contributor
                )
            )
        except AssertionError as e:
            print(f"Failed to delete reverse contributor index: {e}")

    for c in coins:
        data[c["denom"]] = data.get(c["denom"], 0) + int(c["amount"])
        # add new reverse index
        _store_data(
            _get_reverse_contributor_index(
                namespace, tag_name, c["denom"], data[c["denom"]], contributor
            ),
            {
                "contributor": contributor,
                "denom": c["denom"],
                "amount": data[c["denom"]],
            },
        )
    _store_data(index, data)


### Indexing Functions ###


def _get_rate_index(namespace: str, tag_name: str, id: int) -> str:
    """Generate the index for storing rates within a namespace."""
    return f"rate_tags/{namespace}/{tag_name}/{_format_id(id)}"


def _get_tag_prefix(namespace: str) -> str:
    return f"tag/{namespace}/"


def _get_tag_index(namespace: str, tag_name: str) -> str:
    if isinstance(tag_name, int):
        tag_name = _format_id(tag_name)
    return _get_tag_prefix(namespace) + tag_name


def _get_reverse_contributor_prefix(namespace: str, tag_name, denom) -> str:
    return f"top_tag_contributor/{namespace}/{tag_name}/{denom}/"


def _get_reverse_contributor_index(namespace, tag_name, denom, amount, contributor):
    return (
        _get_reverse_contributor_prefix(namespace, tag_name, denom)
        + f"{amount:015}/{contributor}"
    )


def _get_tag_contributor_prefix(namespace: str) -> str:
    return f"tag_contributor/{namespace}/"


def _get_tag_contributor_index(namespace, tag_name, contributor):
    return _get_tag_contributor_prefix(namespace) + f"{tag_name}/{contributor}"


def _get_rating_rate_prefix(namespace: str, tag_name: str, rating_type: str) -> str:
    """Index for storing score-based rates, supporting both 'best' and 'hot' types."""
    return f"rate/{namespace}/{tag_name}/{rating_type}/"


def _get_rating_rate_index(
    namespace: str, tag_name: str, rating_type: str, score: float, id: int
) -> str:
    """Index for storing score-based rates, supporting both 'best' and 'hot' types."""
    return (
        _get_rating_rate_prefix(namespace, tag_name, rating_type)
        + f"{score:012.05f}/{_format_id(id)}"
    )


def _get_reverse_rating_prefix(namespace: str, id: int, rating_type: str) -> str:
    """Prefix for reverse indexing of scored tags on a namespaced object ID."""
    return f"reverse_rates/{namespace}/{_format_id(id)}/{rating_type}/"


def _get_reverse_rating_index(
    namespace: str, id: int, tag_name: str, rating_type: str, score: float
) -> str:
    """Index for reverse relationship of scored tag on namespaced object ID."""
    return (
        _get_reverse_rating_prefix(namespace, id, rating_type)
        + f"{score:012.05f}/{tag_name}"
    )


def _delete_rating_index(rate_data):
    """Delete old score indexes for a rate."""
    try:
        _delete_data(
            _get_rating_rate_index(
                rate_data["namespace"],
                rate_data["tag_name"],
                "best",
                rate_data["best_rating"],
                rate_data["id"],
            )
        )
    except Exception as e:
        print(f"Failed to delete best rating index: {e}")
        pass
    try:
        _delete_data(
            _get_rating_rate_index(
                rate_data["namespace"],
                rate_data["tag_name"],
                "hot",
                rate_data["hot_rating"],
                rate_data["id"],
            )
        )
    except Exception as e:
        print(f"Failed to delete hot rating index: {e}")
        pass


def _delete_reverse_rating_index(rate_data):
    """Delete old reverse score indexes for a rate."""
    try:
        _delete_data(
            _get_reverse_rating_index(
                rate_data["namespace"],
                rate_data["id"],
                rate_data["tag_name"],
                "best",
                rate_data["best_rating"],
            )
        )
    except Exception as e:
        print(f"Failed to delete reverse best rating index: {e}")
        pass
    try:
        _delete_data(
            _get_reverse_rating_index(
                rate_data["namespace"],
                rate_data["id"],
                rate_data["tag_name"],
                "hot",
                rate_data["hot_rating"],
            )
        )
    except Exception as e:
        print(f"Failed to delete reverse hot rating index: {e}")
        pass


def _set_rating_index(rate_data):
    """Set new score indexes for a rate."""
    _store_data(
        _get_rating_rate_index(
            rate_data["namespace"],
            rate_data["tag_name"],
            "best",
            rate_data["best_rating"],
            rate_data["id"],
        ),
        {
            "id": rate_data["id"],
            "best_rating": rate_data["best_rating"],
            "metadata": rate_data["metadata"],
        },
    )
    _store_data(
        _get_rating_rate_index(
            rate_data["namespace"],
            rate_data["tag_name"],
            "hot",
            rate_data["hot_rating"],
            rate_data["id"],
        ),
        {
            "id": rate_data["id"],
            "hot_rating": rate_data["hot_rating"],
            "metadata": rate_data["metadata"],
        },
    )


def _set_reverse_rating_index(rate_data):
    """Set reverse score indexes for a rate."""
    _store_data(
        _get_reverse_rating_index(
            rate_data["namespace"],
            rate_data["id"],
            rate_data["tag_name"],
            "best",
            rate_data["best_rating"],
        ),
        {"tag_name": rate_data["tag_name"]},
    )
    _store_data(
        _get_reverse_rating_index(
            rate_data["namespace"],
            rate_data["id"],
            rate_data["tag_name"],
            "hot",
            rate_data["hot_rating"],
        ),
        {"tag_name": rate_data["tag_name"]},
    )


##################
###  Rewards ##
##################
REPLIES = "replies"
TAGS = "tags"


def claim_reply_rewards(post_id: int, hot_index: int):
    return _claim_rewards(_format_id(post_id), hot_index, REPLIES)


def claim_tag_rewards(tag_name: str, hot_index: int):
    return _claim_rewards(tag_name, hot_index, TAGS)


def debug_hot_list(
    tag_name: str, reverse: bool = False, offset: int = 0, limit: int = 10
):
    """Debug function to inspect the hot list contents for a tag."""
    print(f"DEBUG debug_hot_list: reverse={reverse}, offset={offset}, limit={limit}")
    prefix = _get_rating_rate_prefix("tags", tag_name, "hot")
    hot_posts, pagination = _list_data(
        prefix,
        pagination={
            "reverse": reverse,
            "offset": offset,
            "limit": limit,
            "count_total": True,
        },
    )

    debug_info = {
        "tag_name": tag_name,
        "hot_list_count": len(hot_posts),
        "hot_posts": [
            {"id": post["id"], "hot_rating": post.get("hot_rating", "N/A")}
            for post in hot_posts
        ],
        "prefix_used": prefix,
    }

    return debug_info


def _claim_rewards(tag_name: str, hot_index: int, namespace: str):
    prefix = _get_rating_rate_prefix(namespace, tag_name, "hot")

    assert (
        10 > hot_index
    ), f"Only the top 10 hot posts can claim rewards, index [{hot_index}] is too low."

    # Fetch the specific hot post using offset-based pagination
    hot_posts, pagination = _list_data(
        prefix, pagination={"offset": hot_index, "limit": 1, "reverse": True}
    )

    assert (
        len(hot_posts) > 0
    ), f"Index[{hot_index}] hot post for tag[{tag_name}] not found."

    # Get the post at the specific hot_index
    hot_post = hot_posts[0]

    post_index = _get_post_index(hot_post["id"])
    post = _get_data(post_index)  # retrieve the post data

    author = post["author"]

    # ensure that only the post author or the owner of the author's name can claim the rewards
    if author != get_caller():
        try:
            name_resp = _query(
                {
                    "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
                    "name_or_address": author,
                }
            )
            destination_address = name_resp["address"]
            assert get_caller() == destination_address
        except Exception as e:
            raise Exception(f'[{get_caller()}] is not authorized for "{author}": {e}')

    reward_index = _get_tag_index(namespace, tag_name)
    try:
        rewards = _get_data(reward_index)
    except AssertionError as e:
        raise Exception(f"no rewards available: {e}")
    _delete_rewards_indexes(namespace, rewards)

    tag_data = _get_post_tag(post["post_id"], tag_name, namespace=namespace)
    assert (
        tag_data is not None
    ), f"Tag data not found for post {post['post_id']}, tag {tag_name}"

    # DEBUG: Print what tag_data we got
    print(
        f"DEBUG _claim_rewards: tag_data for post {post['post_id']}: earliest_claim_time={tag_data['metadata']}"
    )

    tag_data["metadata"]["claimed"] = tag_data["metadata"].get("claimed", {})
    earliest_claim_time = tag_data["metadata"].get("earliest_claim_time", 0)

    now = int(datetime.now().timestamp())

    assert (
        now >= earliest_claim_time
    ), f"You must wait [{earliest_claim_time - now}]seconds to claim rewards for tag[{tag_name}] of post[{post['post_id']}]."

    earliest_claim_time = now + CLAIM_WAIT_SEC
    tag_data["metadata"]["last_claimed"] = now
    tag_data["metadata"]["earliest_claim_time"] = earliest_claim_time

    reward_power = Decimal(1) / (Decimal(2) ** (Decimal(hot_index) + Decimal(1)))
    author_rewards = {}

    profile_data = _get_profile(author)
    profile_data["claimed"] = profile_data.get("claimed", {})
    post["claimed"] = post.get("claimed", {})
    for denom, amount in rewards["available"].items():
        reward_amount = int(Decimal(amount) * reward_power)
        author_rewards[denom] = reward_amount

        _msg(
            {
                "@type": "/cosmos.bank.v1beta1.MsgSend",
                "from_address": get_script_address(),
                "to_address": get_caller(),
                "amount": [{"amount": str(reward_amount), "denom": denom}],
            }
        )

        # update available rewards
        rewards["available"][denom] -= reward_amount
        rewards["claimed"][denom] = rewards["claimed"].get(denom, 0) + reward_amount

        # store on post tag
        tag_data["metadata"]["claimed"][denom] = (
            tag_data["metadata"]["claimed"].get(denom, 0) + reward_amount
        )
        post["claimed"][denom] = post["claimed"].get(denom, 0) + reward_amount
        profile_data["claimed"][denom] = (
            profile_data["claimed"].get(denom, 0) + reward_amount
        )

    _store_data(post_index, post)
    _store_data(_get_author_profile_index(author), profile_data)
    _store_data(_get_rate_index(namespace, tag_name, post["post_id"]), tag_data)
    _store_data(reward_index, rewards)
    _set_rewards_indexes(namespace, rewards)
    if namespace == TAGS:
        block_info = get_block_info()
        _store_data(
            _get_post_tag_historical_rewards_prefix(
                tag_name, post["post_id"], block_info["time"], namespace=namespace
            ),
            {
                "hot_index": hot_index,
                "author_rewards": author_rewards,
                "up": tag_data["up"],
                "down": tag_data["down"],
            },
        )
    return {"reward_power": str(reward_power), "author_rewards": author_rewards}


def _get_post_tag_historical_rewards_prefix(
    tag_name: str | None = None,
    post_id: int | None = None,
    time: str | None = None,
    author: str | None = None,
    namespace=TAGS,
) -> str:
    prefix = "historical_rewards"
    path_parts = [prefix, namespace]

    if tag_name is not None:
        path_parts.append(tag_name)
    if post_id is not None:
        path_parts.append(_format_id(post_id))
    if time is not None:
        path_parts.append(str(time))

    return "/".join(path_parts)


def add_tag_rewards(tag_name: str, contributor: str = ""):
    coins = get_coins_sent()
    _add_rewards(tag_name, coins, TAGS, contributor)


def _add_rewards(tag_name, coins, namespace, contributor):

    if not contributor:
        contributor = get_caller()
    else:
        name_resp = _query(
            {
                "@type": "/dysonprotocol.nameservice.v1.QueryResolveNameRequest",
                "name_or_address": contributor,
            }
        )
        destination_address = name_resp["address"]
        assert (
            get_caller() == destination_address
        ), f"[{get_caller()}] is not authorized for contributor name: {contributor}"
    index = _get_tag_index(namespace, tag_name)

    try:
        rewards = _get_data(index)
    except Exception as e:
        print(f"Tag rewards not found: {e}")
        rewards = {"available": {}, "claimed": {}, "tag_name": tag_name}

    _delete_rewards_indexes(namespace, rewards)

    for coin in coins:
        old_amount = rewards["available"].get(coin["denom"], 0)
        rewards["available"][coin["denom"]] = old_amount + int(coin["amount"])

    _store_data(index, rewards)
    _set_rewards_indexes(namespace, rewards)
    if namespace == TAGS:
        _track_contributor_rewards(namespace, tag_name, coins, contributor=contributor)


def _available_reward_prefix(namespace):
    return f"available_rewards/{namespace}/"


def _available_reward_index(namespace, tag_name, denom, available_rewards):
    return (
        _available_reward_prefix(namespace)
        + f"{denom}/{available_rewards:015}/{tag_name}"
    )


def _delete_rewards_indexes(namespace, rewards):
    for denom, amount in rewards["available"].items():
        index = _available_reward_index(namespace, rewards["tag_name"], denom, amount)
        try:
            _delete_data(index)
        except Exception as e:
            print(f"Failed to delete rewards index: {e}")
            pass


def _set_rewards_indexes(namespace, rewards):
    for denom, amount in rewards["available"].items():
        index = _available_reward_index(namespace, rewards["tag_name"], denom, amount)
        _store_data(
            index, {"tag_name": rewards["tag_name"], "denom": denom, "amount": amount}
        )


def _get_profile(author_name):
    try:
        profile_index = _get_author_profile_index(author_name)
        profile_data = _get_data(profile_index)
        print(
            f"Successfully retrieved profile for {author_name}: content length = {len(profile_data.get('content', ''))}"
        )
        return profile_data
    except Exception as e:
        print(
            f"Profile not found for {author_name} at index {_get_author_profile_index(author_name)}: {e}"
        )
        return {"content": "", "claimed": {}}


def _get_best_tags_by_post_id(post_id: int, **kwargs):
    prefix = _get_reverse_rating_prefix("tags", post_id, "best")
    return _list_data(prefix, **kwargs)


def _get_post_tag(post_id: int, tag_name: str, namespace="tags"):
    try:
        tag_index = _get_rate_index(namespace, tag_name, post_id)
        return _get_data(tag_index)
    except DysQueryException as e:
        print(f"Could not find tag '{tag_name}' for post {post_id}: {e}")
        return None


def _get_best_replies_by_post_id(post_id: int, **kwargs):
    prefix = _get_rating_rate_prefix("replies", _format_id(post_id), "best")
    return _list_data(prefix, **kwargs)


def _get_post_reply(post_id: int, reply_post_id: int):
    tag_index = _get_rate_index("replies", _format_id(post_id), reply_post_id)
    return _get_data(tag_index)

