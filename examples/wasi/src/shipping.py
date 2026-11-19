from sys import argv


def shipping_fee(subtotal_cents: int) -> int:
    if subtotal_cents >= 5_000:
        return 0
    return 500


if __name__ == "__main__":  # pragma: no branch
    print(shipping_fee(int(argv[1])))
