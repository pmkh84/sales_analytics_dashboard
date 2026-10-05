from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import CreatedSale, CreateSaleRequest, CustomerOption, ProductOption
from app.services import sales

router = APIRouter(prefix="/api", tags=["Sales"])
Database = Annotated[Session, Depends(get_db)]


@router.get("/customers", response_model=list[CustomerOption])
def get_customers(db: Database):
    return sales.customers(db)


@router.get("/products", response_model=list[ProductOption])
def get_products(db: Database):
    return sales.products(db)


@router.post("/sales", response_model=CreatedSale, status_code=201)
def create_sale(request: CreateSaleRequest, db: Database):
    return sales.create_sale(db, request)


@router.delete("/sales/{sale_id}", status_code=204, response_class=Response)
def delete_sale(sale_id: Annotated[int, Path(gt=0, le=2147483647)], db: Database):
    sales.delete_sale(db, sale_id)
    return Response(status_code=204)


@router.patch("/sales/{sale_id}", response_model=CreatedSale)
def update_sale(
    sale_id: Annotated[int, Path(gt=0, le=2147483647)], request: CreateSaleRequest, db: Database,
):
    return sales.update_sale(db, sale_id, request)
