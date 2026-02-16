import os
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from marshmallow import ValidationError, fields, validate
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

load_dotenv()

# -----------------------------
# App + DB setup
# -----------------------------
app = Flask(__name__)

DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "ecommerce_api")

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+mysqlconnector://root:00001487@localhost/ecommerce_api"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
db.init_app(app)
ma = Marshmallow(app)

# -----------------------------
# Association Table (no duplicates)
# -----------------------------
class OrderProduct(db.Model):
    __tablename__ = "order_product"

    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )

    # Composite PK already prevents duplicates.
    # This UniqueConstraint is optional/redundant, but explicit:
    __table_args__ = (UniqueConstraint("order_id", "product_id", name="uq_order_product"),)


# -----------------------------
# Models
# -----------------------------
class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)

    orders: Mapped[list["Order"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Order(db.Model):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    user: Mapped["User"] = relationship(back_populates="orders")

    products: Mapped[list["Product"]] = relationship(
        secondary="order_product",
        back_populates="orders",
    )


class Product(db.Model):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_name: Mapped[str] = mapped_column(String(120), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)

    orders: Mapped[list["Order"]] = relationship(
        secondary="order_product",
        back_populates="products",
    )


# -----------------------------
# Schemas (Marshmallow)
# -----------------------------
class UserSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = User
        load_instance = True
        ordered = True

    email = fields.Email(required=True)
    name = fields.String(required=True, validate=validate.Length(min=1))
    address = fields.String(required=True, validate=validate.Length(min=1))


class ProductSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Product
        load_instance = True
        ordered = True

    product_name = fields.String(required=True, validate=validate.Length(min=1))
    price = fields.Float(required=True, validate=validate.Range(min=0))


class OrderSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Order
        load_instance = True
        ordered = True
        include_fk = True  # IMPORTANT: makes user_id appear

    user_id = fields.Integer(required=True, strict=True)
    order_date = fields.DateTime(required=True)


user_schema = UserSchema()
users_schema = UserSchema(many=True)

product_schema = ProductSchema()
products_schema = ProductSchema(many=True)

order_schema = OrderSchema()
orders_schema = OrderSchema(many=True)


# -----------------------------
# Helpers
# -----------------------------
def error(message: str, status: int = 400):
    return jsonify({"error": message}), status


@app.errorhandler(ValidationError)
def handle_validation_error(err):
    return jsonify({"error": "ValidationError", "messages": err.messages}), 400


# -----------------------------
# USER CRUD
# -----------------------------
@app.get("/users")
def get_users():
    users = db.session.query(User).all()
    return jsonify(users_schema.dump(users)), 200


@app.get("/users/<int:user_id>")
def get_user(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return error("User not found", 404)
    return jsonify(user_schema.dump(user)), 200


@app.post("/users")
def create_user():
    data = request.get_json(force=True)
    user = user_schema.load(data)  # validates + creates instance

    # Enforce unique email check (nice message vs DB crash)
    existing = db.session.query(User).filter_by(email=user.email).first()
    if existing:
        return error("Email already exists", 409)

    db.session.add(user)
    db.session.commit()
    return jsonify(user_schema.dump(user)), 201


@app.put("/users/<int:user_id>")
def update_user(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return error("User not found", 404)

    data = request.get_json(force=True)

    # partial update allowed
    loaded = user_schema.load(data, partial=True)

    if "email" in data:
        existing = db.session.query(User).filter(User.email == data["email"], User.id != user_id).first()
        if existing:
            return error("Email already exists", 409)

    for key, value in data.items():
        setattr(user, key, value)

    db.session.commit()
    return jsonify(user_schema.dump(user)), 200


@app.delete("/users/<int:user_id>")
def delete_user(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return error("User not found", 404)

    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User deleted"}), 200


# -----------------------------
# PRODUCT CRUD
# -----------------------------
@app.get("/products")
def get_products():
    products = db.session.query(Product).all()
    return jsonify(products_schema.dump(products)), 200


@app.get("/products/<int:product_id>")
def get_product(product_id: int):
    product = db.session.get(Product, product_id)
    if not product:
        return error("Product not found", 404)
    return jsonify(product_schema.dump(product)), 200


@app.post("/products")
def create_product():
    data = request.get_json(force=True)
    product = product_schema.load(data)
    db.session.add(product)
    db.session.commit()
    return jsonify(product_schema.dump(product)), 201


@app.put("/products/<int:product_id>")
def update_product(product_id: int):
    product = db.session.get(Product, product_id)
    if not product:
        return error("Product not found", 404)

    data = request.get_json(force=True)
    _ = product_schema.load(data, partial=True)  # validate only

    for key, value in data.items():
        setattr(product, key, value)

    db.session.commit()
    return jsonify(product_schema.dump(product)), 200


@app.delete("/products/<int:product_id>")
def delete_product(product_id: int):
    product = db.session.get(Product, product_id)
    if not product:
        return error("Product not found", 404)

    db.session.delete(product)
    db.session.commit()
    return jsonify({"message": "Product deleted"}), 200


# -----------------------------
# ORDER endpoints
# -----------------------------
@app.post("/orders")
def create_order():
    data = request.get_json(force=True)

    # Validate basic payload
    new_order = order_schema.load(data)

    # Verify user exists
    user = db.session.get(User, new_order.user_id)
    if not user:
        return error("User not found for user_id", 404)

    order = Order(order_date=new_order.order_date, user_id=new_order.user_id)
    db.session.add(order)
    db.session.commit()
    return jsonify(order_schema.dump(order)), 201


@app.put("/orders/<int:order_id>/add_product/<int:product_id>")
def add_product_to_order(order_id: int, product_id: int):
    order = db.session.get(Order, order_id)
    if not order:
        return error("Order not found", 404)

    product = db.session.get(Product, product_id)
    if not product:
        return error("Product not found", 404)

    # Prevent duplicates
    if product in order.products:
        return error("Product already in this order", 409)

    order.products.append(product)
    db.session.commit()

    return jsonify({"message": "Product added", "order_id": order_id, "product_id": product_id}), 200


@app.delete("/orders/<int:order_id>/remove_product/<int:product_id>")
def remove_product_from_order(order_id: int, product_id: int):
    order = db.session.get(Order, order_id)
    if not order:
        return error("Order not found", 404)

    product = db.session.get(Product, product_id)
    if not product:
        return error("Product not found", 404)

    if product not in order.products:
        return error("Product not in this order", 404)

    order.products.remove(product)
    db.session.commit()

    return jsonify({"message": "Product removed", "order_id": order_id, "product_id": product_id}), 200


@app.get("/orders/user/<int:user_id>")
def get_orders_for_user(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return error("User not found", 404)

    return jsonify(orders_schema.dump(user.orders)), 200


@app.get("/orders/<int:order_id>/products")
def get_products_for_order(order_id: int):
    order = db.session.get(Order, order_id)
    if not order:
        return error("Order not found", 404)

    return jsonify(products_schema.dump(order.products)), 200

@app.delete("/orders/<int:order_id>")
def delete_order(order_id: int):
    order = db.session.get(Order, order_id)
    if not order:
        return error("Order not found", 404)

    db.session.delete(order)
    db.session.commit()
    return jsonify({"message": "Order deleted"}), 200

# -----------------------------
# Create tables + run
# -----------------------------
with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
    