"""Hardcoded data for testing"""
ORDERS: dict[str,dict] = {
    "ORDER-SMALL-001": {
        "customer_id": "CUST-101",
        "customer_name": "Alice Johnson",
        "item_name": "USB-C Laptop Stand",
        "order_value": 149.99,
        "order_date": "2026-08-01", # 17 days agove within 30 days window
        "return_window_days": 30
    },
    "ORDER-MID-002": {
        "customer_id": "CUST-102",
        "customer_name": "Bob Chen",
        "item_name": "ProBook Business Laptop",
        "order_value": 1299.00,
        "order_date": "2026-08-03", # 15 days agove within 30 days window
        "return_window_days": 30
    },
    "ORDER-LARGE-003": {
        "customer_id": "CUST-103",
        "customer_name": "Carol Davis",
        "item_name": "Developer Workstation",
        "order_value": 2499.00,
        "order_date": "2026-08-11", # 8 days agove within 30 days window
        "return_window_days": 30
    },
    "ORDER-EXPIRED-004": {
        "customer_id": "CUST-104",
        "customer_name": "David Park",
        "item_name": "Wireless Keyboard",
        "order_value": 89.99,
        "order_date": "2026-06-01", # 87 days ago outside 30 day window of return
        "return_window_days": 30
    }
}