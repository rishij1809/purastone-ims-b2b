class InsufficientStockError(Exception):
    """Raised when unexpired stock is insufficient for an outtake or adjustment."""
    pass

class InvalidAdjustmentError(ValueError):
    """Raised when adjustment parameters (e.g., reason code) are invalid."""
    pass

class ProductNotFoundError(Exception):
    """Raised when a requested SKU does not exist in Product or BundleMapping."""
    pass

class NegativeMarginError(ValueError):
    """Raised when a discount results in a selling price below the product COGS floor."""
    pass
