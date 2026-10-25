#!/usr/bin/env python3
"""
Deterministic Database Seeder for High-Performance Product Catalog API.
Populates hierarchical categories, brands, and 1,000+ realistic products.
"""

from __future__ import annotations

import os
import random
import sys
import pymysql

# Configuration
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3307"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "catalog_db")
DB_SOCKET = os.getenv("DB_SOCKET", "/tmp/mysql3307.sock")


def get_db_connection():
    if os.path.exists(DB_SOCKET):
        return pymysql.connect(
            unix_socket=DB_SOCKET,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def seed():
    random.seed(42)  # Deterministic seed
    conn = get_db_connection()
    cursor = conn.cursor()

    print("[1/3] Seeding Categories...")
    # Roots
    root_categories = [
        ("Electronics", "electronics"),
        ("Home & Kitchen", "home-kitchen"),
        ("Fashion & Lifestyle", "fashion-lifestyle"),
    ]
    cat_map = {}
    for name, slug in root_categories:
        cursor.execute(
            """
            INSERT INTO categories (name, slug, parent_id)
            VALUES (%s, %s, NULL)
            ON DUPLICATE KEY UPDATE name=VALUES(name)
            """,
            (name, slug),
        )
        cursor.execute("SELECT id FROM categories WHERE slug = %s", (slug,))
        cat_map[slug] = cursor.fetchone()["id"]

    # Subcategories
    subcategories = [
        # Electronics
        ("Audio & Headphones", "audio-headphones", "electronics"),
        ("Laptops & Computers", "laptops-computers", "electronics"),
        ("Smartphones & Tablets", "smartphones-tablets", "electronics"),
        ("Cameras & Optics", "cameras-optics", "electronics"),
        # Home & Kitchen
        ("Kitchen Appliances", "kitchen-appliances", "home-kitchen"),
        ("Living Room Furniture", "living-room-furniture", "home-kitchen"),
        ("Cookware & Dining", "cookware-dining", "home-kitchen"),
        ("Home Decor", "home-decor", "home-kitchen"),
        # Fashion
        ("Footwear & Sneakers", "footwear-sneakers", "fashion-lifestyle"),
        ("Men Apparel", "men-apparel", "fashion-lifestyle"),
        ("Women Apparel", "women-apparel", "fashion-lifestyle"),
        ("Watches & Accessories", "watches-accessories", "fashion-lifestyle"),
    ]
    subcat_ids = []
    for name, slug, parent_slug in subcategories:
        parent_id = cat_map[parent_slug]
        cursor.execute(
            """
            INSERT INTO categories (name, slug, parent_id)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE name=VALUES(name), parent_id=VALUES(parent_id)
            """,
            (name, slug, parent_id),
        )
        cursor.execute("SELECT id FROM categories WHERE slug = %s", (slug,))
        cid = cursor.fetchone()["id"]
        cat_map[slug] = cid
        subcat_ids.append(cid)

    print(f"  -> Seeded {len(cat_map)} categories (hierarchical tree).")

    print("[2/3] Seeding Brands...")
    brands_data = [
        ("Sony", "sony", "Japan"),
        ("Apple", "apple", "USA"),
        ("Samsung", "samsung", "South Korea"),
        ("Dell", "dell", "USA"),
        ("Bose", "bose", "USA"),
        ("Philips", "philips", "Netherlands"),
        ("Nike", "nike", "USA"),
        ("Adidas", "adidas", "Germany"),
        ("Puma", "puma", "Germany"),
        ("Titan", "titan", "India"),
        ("Havells", "havells", "India"),
        ("IKEA", "ikea", "Sweden"),
        ("Logitech", "logitech", "Switzerland"),
        ("Canon", "canon", "Japan"),
        ("Prestige", "prestige", "India"),
    ]
    brand_ids = []
    for name, slug, country in brands_data:
        cursor.execute(
            """
            INSERT INTO brands (name, slug, country)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE country=VALUES(country)
            """,
            (name, slug, country),
        )
        cursor.execute("SELECT id FROM brands WHERE slug = %s", (slug,))
        brand_ids.append(cursor.fetchone()["id"])

    print(f"  -> Seeded {len(brand_ids)} brands.")

    print("[3/3] Seeding 1,000 Products...")
    # Product title descriptors
    adjectives = ["Pro", "Ultra", "Max", "Air", "Prime", "Elite", "Classic", "Wireless", "Compact", "Gaming", "Smart", "Eco", "Ergonomic"]
    nouns = {
        "audio-headphones": ["Noise-Cancelling Headphones", "In-Ear Earbuds", "Bluetooth Speaker", "Studio Monitor", "Wireless Neckband"],
        "laptops-computers": ["Ultrabook Laptop", "Gaming Desktop", "4K HDR Monitor", "Mechanical Keyboard", "USB-C Multiport Dock"],
        "smartphones-tablets": ["5G Flagship Phone", "OLED Tablet", "Wireless Fast Charger", "Rugged Protective Case"],
        "cameras-optics": ["Mirrorless 4K Camera", "50mm Prime Lens", "Travel Tripod", "Action Camera 60FPS"],
        "kitchen-appliances": ["Air Fryer Oven", "Espresso Coffee Maker", "High-Power Blender", "Electric Induction Cooktop"],
        "living-room-furniture": ["Ergonomic Recliner", "Solid Wood Coffee Table", "Modular Bookshelf", "Accent Lounge Chair"],
        "cookware-dining": ["Tri-Ply Stainless Steel Pan", "Cast Iron Skillet", "Non-Stick Chef Wok", "16-Piece Dinner Set"],
        "home-decor": ["Ceramic Floor Vase", "Warm Ambient Floor Lamp", "Geometric Wool Rug", "Minimalist Wall Clock"],
        "footwear-sneakers": ["Cushioned Running Shoes", "Retro Leather Sneakers", "Waterproof Trail Boots", "Slip-On Loafers"],
        "men-apparel": ["Slim Fit Oxford Shirt", "Merino Wool Sweater", "Comfort Chino Trousers", "Lightweight Rain Jacket"],
        "women-apparel": ["Breathable Cotton Blouse", "Tailored Formal Blazer", "High-Waist Yoga Leggings", "Cashmere Scarf"],
        "watches-accessories": ["Chronograph Analog Watch", "Fitness Tracker Smartwatch", "Genuine Leather Wallet", "Aviator Polarized Sunglasses"],
    }

    # Generate 1,000 products
    products = []
    prod_idx = 1

    for slug, cid in cat_map.items():
        if slug in ["electronics", "home-kitchen", "fashion-lifestyle"]:
            continue  # Only assign products directly to leaves
        cat_nouns = nouns.get(slug, ["Item"])
        for _ in range(85):  # ~85 per leaf category = 1,020 total
            adj = random.choice(adjectives)
            noun = random.choice(cat_nouns)
            brand_id = random.choice(brand_ids)
            model_num = random.randint(100, 999)
            title = f"{adj} {noun} {model_num}"
            sku = f"SKU-{slug[:3].upper()}-{brand_id:02d}-{prod_idx:05d}"
            prod_slug = f"{slug}-{adj.lower()}-{noun.lower().replace(' ', '-')}-{model_num}-{prod_idx}"
            desc = f"Premium quality {title} designed for high performance, reliability, and modern lifestyle standards."
            price = round(random.uniform(499.0, 89999.0), 2)
            stock = random.randint(0, 500)
            rating = round(random.uniform(3.0, 5.0), 2)
            is_active = random.random() > 0.05  # 95% active

            products.append((
                sku, title, prod_slug, desc, price, "INR", stock, cid, brand_id, rating, is_active, 1
            ))
            prod_idx += 1

    # Bulk insert in batches of 200
    batch_size = 200
    insert_sql = """
        INSERT INTO products (
            sku, title, slug, description, price, currency, stock_quantity,
            category_id, brand_id, rating, is_active, version
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            title=VALUES(title),
            price=VALUES(price),
            stock_quantity=VALUES(stock_quantity),
            rating=VALUES(rating),
            is_active=VALUES(is_active)
    """

    for i in range(0, len(products), batch_size):
        batch = products[i:i + batch_size]
        cursor.executemany(insert_sql, batch)

    cursor.execute("SELECT count(*) as cnt FROM products")
    total_prods = cursor.fetchone()["cnt"]
    print(f"  -> Successfully seeded {total_prods} products in catalog_db!")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    seed()
