def shipping_fee(subtotal: int) -> int:
    if subtotal >= 100:
        return 0
    return 15
