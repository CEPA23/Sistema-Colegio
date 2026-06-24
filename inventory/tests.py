from decimal import Decimal

from django.test import TestCase

from .models import Product


class ProductAutoCodeTests(TestCase):
    def test_auto_generates_code_and_barcode_for_book(self):
        product = Product.objects.create(
            code='',
            name='Libro de Prueba',
            category=Product.CATEGORY_BOOK,
            price=Decimal('25.00'),
            stock=2,
            stock_min=1,
            stock_max=10,
        )

        self.assertTrue(product.code.startswith('LIB-'))
        self.assertTrue(product.barcode)
        self.assertEqual(product.category, Product.CATEGORY_BOOK)
