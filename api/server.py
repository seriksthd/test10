from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime
import shutil
from enum import Enum

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Create uploads directory
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Mount static files for uploads
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Security
security = HTTPBearer()
ADMIN_TOKEN = "admin_secret_key_2024"  # In production, use environment variable

# Enums
class OrderStatus(str, Enum):
    PENDING = "Даярдалып жатат"
    READY = "Даяр"
    DELIVERED = "Жеткирилди"
    CANCELLED = "Жокко чыгарылган"

# Define Models
class Product(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    price: float
    image: str
    category: str
    description: str = ""
    isFavorite: bool = False
    is_available: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class ProductCreate(BaseModel):
    name: str
    price: float
    image: str
    category: str
    description: str = ""

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    image: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    is_available: Optional[bool] = None

class CartItem(BaseModel):
    product_id: str
    product_name: str
    price: float
    quantity: int
    image: str

class Order(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    customer_name: str
    phone: str
    cart_items: List[CartItem]
    total: float
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class OrderCreate(BaseModel):
    customer_name: str
    phone: str
    cart_items: List[CartItem]
    total: float

class OrderStatusUpdate(BaseModel):
    status: OrderStatus

class GalleryImage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    url: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)

class AdminStats(BaseModel):
    total_products: int
    total_orders: int
    total_sales: float
    pending_orders: int
    today_orders: int
    today_sales: float

# Authentication helper
def verify_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    return credentials.credentials

# Product routes
@api_router.post("/products", response_model=Product)
async def create_product(product: ProductCreate, admin_token: str = Depends(verify_admin_token)):
    product_dict = product.dict()
    product_obj = Product(**product_dict)
    await db.products.insert_one(product_obj.dict())
    return product_obj

@api_router.get("/products", response_model=List[Product])
async def get_products():
    products = await db.products.find().to_list(1000)
    return [Product(**product) for product in products]

@api_router.get("/products/category/{category}", response_model=List[Product])
async def get_products_by_category(category: str):
    products = await db.products.find({"category": category}).to_list(1000)
    return [Product(**product) for product in products]

@api_router.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str):
    product = await db.products.find_one({"id": product_id})
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return Product(**product)

@api_router.put("/products/{product_id}", response_model=Product)
async def update_product(product_id: str, product_update: ProductUpdate, admin_token: str = Depends(verify_admin_token)):
    product = await db.products.find_one({"id": product_id})
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    
    update_data = product_update.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow()
    
    await db.products.update_one({"id": product_id}, {"$set": update_data})
    updated_product = await db.products.find_one({"id": product_id})
    return Product(**updated_product)

@api_router.delete("/products/{product_id}")
async def delete_product(product_id: str, admin_token: str = Depends(verify_admin_token)):
    result = await db.products.delete_one({"id": product_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"message": "Product deleted successfully"}

@api_router.put("/products/{product_id}/favorite")
async def toggle_favorite(product_id: str):
    product = await db.products.find_one({"id": product_id})
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    
    new_favorite_status = not product.get("isFavorite", False)
    await db.products.update_one(
        {"id": product_id},
        {"$set": {"isFavorite": new_favorite_status}}
    )
    return {"message": "Favorite status updated", "isFavorite": new_favorite_status}

# Order routes
@api_router.post("/orders", response_model=Order)
async def create_order(order: OrderCreate):
    order_dict = order.dict()
    order_obj = Order(**order_dict)
    await db.orders.insert_one(order_obj.dict())
    return order_obj

@api_router.get("/orders", response_model=List[Order])
async def get_orders():
    orders = await db.orders.find().sort("created_at", -1).to_list(1000)
    return [Order(**order) for order in orders]

@api_router.get("/orders/{order_id}", response_model=Order)
async def get_order(order_id: str):
    order = await db.orders.find_one({"id": order_id})
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return Order(**order)

@api_router.put("/orders/{order_id}/status")
async def update_order_status(order_id: str, status_update: OrderStatusUpdate, admin_token: str = Depends(verify_admin_token)):
    order = await db.orders.find_one({"id": order_id})
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"status": status_update.status, "updated_at": datetime.utcnow()}}
    )
    return {"message": "Order status updated", "status": status_update.status}

@api_router.get("/orders/status/{status}", response_model=List[Order])
async def get_orders_by_status(status: OrderStatus):
    orders = await db.orders.find({"status": status}).sort("created_at", -1).to_list(1000)
    return [Order(**order) for order in orders]

# Gallery routes
@api_router.post("/gallery/upload")
async def upload_image(file: UploadFile = File(...), admin_token: str = Depends(verify_admin_token)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Generate unique filename
    file_extension = file.filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{file_extension}"
    file_path = UPLOAD_DIR / filename
    
    # Save file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Save to database
    image_url = f"/uploads/{filename}"
    gallery_image = GalleryImage(filename=filename, url=image_url)
    await db.gallery.insert_one(gallery_image.dict())
    
    return {"url": image_url, "filename": filename}

@api_router.get("/gallery", response_model=List[GalleryImage])
async def get_gallery_images():
    images = await db.gallery.find().sort("uploaded_at", -1).to_list(1000)
    return [GalleryImage(**image) for image in images]

@api_router.delete("/gallery/{image_id}")
async def delete_gallery_image(image_id: str, admin_token: str = Depends(verify_admin_token)):
    image = await db.gallery.find_one({"id": image_id})
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Delete file from disk
    file_path = UPLOAD_DIR / image["filename"]
    if file_path.exists():
        file_path.unlink()
    
    # Delete from database
    await db.gallery.delete_one({"id": image_id})
    return {"message": "Image deleted successfully"}

# Admin routes
@api_router.get("/admin/stats", response_model=AdminStats)
async def get_admin_stats(admin_token: str = Depends(verify_admin_token)):
    from datetime import datetime, timedelta
    
    # Get today's date range
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    # Count totals
    total_products = await db.products.count_documents({})
    total_orders = await db.orders.count_documents({})
    pending_orders = await db.orders.count_documents({"status": OrderStatus.PENDING})
    today_orders = await db.orders.count_documents({
        "created_at": {"$gte": today, "$lt": tomorrow}
    })
    
    # Calculate sales
    all_orders = await db.orders.find().to_list(1000)
    total_sales = sum(order.get("total", 0) for order in all_orders)
    
    today_orders_data = await db.orders.find({
        "created_at": {"$gte": today, "$lt": tomorrow}
    }).to_list(1000)
    today_sales = sum(order.get("total", 0) for order in today_orders_data)
    
    return AdminStats(
        total_products=total_products,
        total_orders=total_orders,
        total_sales=total_sales,
        pending_orders=pending_orders,
        today_orders=today_orders,
        today_sales=today_sales
    )

# Initialize sample data
@api_router.post("/initialize-data")
async def initialize_sample_data():
    # Check if products already exist
    existing_products = await db.products.find().to_list(1)
    if existing_products:
        return {"message": "Sample data already exists"}
    
    # Sample products
    sample_products = [
        {
            "name": "Маргарита Пицца",
            "price": 450.0,
            "image": "https://images.unsplash.com/photo-1611915365928-565c527a0590",
            "category": "pizza",
            "description": "Классикалык пицца моццарелла жана помидор менен"
        },
        {
            "name": "Чизбургер",
            "price": 250.0,
            "image": "https://images.pexels.com/photos/18866153/pexels-photo-18866153.jpeg",
            "category": "burger",
            "description": "Сыр, котлет жана жашылча менен"
        },
        {
            "name": "Капучино",
            "price": 120.0,
            "image": "https://images.pexels.com/photos/312418/pexels-photo-312418.jpeg",
            "category": "coffee",
            "description": "Ысык кофе сүт көбүгү менен"
        },
        {
            "name": "Шоколад Десерт",
            "price": 180.0,
            "image": "https://images.pexels.com/photos/2638026/pexels-photo-2638026.jpeg",
            "category": "dessert",
            "description": "Шоколадтуу таттуу десерт"
        },
        {
            "name": "Латте",
            "price": 140.0,
            "image": "https://images.pexels.com/photos/549222/pexels-photo-549222.jpeg",
            "category": "coffee",
            "description": "Кофе сүт жана көбүк менен"
        },
        {
            "name": "Пепперони Пицца",
            "price": 520.0,
            "image": "https://images.unsplash.com/photo-1611915365928-565c527a0590",
            "category": "pizza",
            "description": "Пепперони жана сыр менен"
        }
    ]
    
    products = []
    for product_data in sample_products:
        product = Product(**product_data)
        products.append(product.dict())
    
    await db.products.insert_many(products)
    return {"message": f"Inserted {len(products)} sample products"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()