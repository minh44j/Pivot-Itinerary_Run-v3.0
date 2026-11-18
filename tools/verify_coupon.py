#!/usr/bin/env python3
"""Check or re-compute a client's personal coupon code from the booking reference.

    PROMO_SECRET='<the GitHub secret>' python tools/verify_coupon.py AJS6F4
    PROMO_SECRET='<the GitHub secret>' python tools/verify_coupon.py AJS6F4 HDUR738HE     # prints VALID / NOT VALID
    (split-carrier booking: pass every reference, comma separated:  B9PS6D,8XMVR7)

The code is HMAC(secret, reference), so it can only be produced or confirmed by someone holding the secret.
Nothing is stored anywhere; the secret itself is never printed.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import promo_page  # noqa: E402


def main(argv):
    if not argv or not os.environ.get("PROMO_SECRET"):
        print(__doc__)
        return 2
    code = promo_page.coupon_code([r for r in argv[0].split(",") if r.strip()], os.environ["PROMO_SECRET"])
    if not code:
        print("No usable reference.")
        return 2
    if len(argv) > 1:
        ok = argv[1].strip().upper() == code
        print("VALID" if ok else "NOT VALID")
        return 0 if ok else 1
    print(code)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
