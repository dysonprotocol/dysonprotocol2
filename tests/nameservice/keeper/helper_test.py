
def get_or_create_key(dysond, name):
    try:
        return dysond("keys", "show", name, "-a").strip()
    except Exception:
        dysond("keys", "add", name)
        return dysond("keys", "show", name, "-a").strip()
