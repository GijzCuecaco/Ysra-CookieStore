from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponseRedirect
from django.urls import reverse
from .models import Product, Category, Cart, CartItem, Order, OrderItem
import uuid
from datetime import datetime

# Check if user is superuser/admin
def is_admin(user):
    return user.is_superuser or user.is_staff

def home(request):
    featured_products = Product.objects.filter(is_featured=True)[:6]
    categories = Category.objects.all()
    context = {
        'featured_products': featured_products,
        'categories': categories
    }
    return render(request, "homepage/home.html", context)


def shop(request):
    """Display all products with filtering and sorting"""
    products = Product.objects.all()
    categories = Category.objects.all()
    
    # Filtering by category
    category_id = request.GET.get('category')
    if category_id:
        products = products.filter(category_id=category_id)
    
    # Sorting
    sort_by = request.GET.get('sort', '-created_at')
    if sort_by in ['name', '-name', 'price', '-price', 'created_at', '-created_at']:
        products = products.order_by(sort_by)
    
    # Search
    search_query = request.GET.get('search')
    if search_query:
        products = products.filter(name__icontains=search_query)
    
    context = {
        'products': products,
        'categories': categories,
        'selected_category': category_id,
        'search_query': search_query
    }
    return render(request, 'homepage/shop.html', context)


def product_detail(request, pk):
    """Display detailed view of a single product"""
    product = get_object_or_404(Product, pk=pk)
    related_products = Product.objects.filter(category=product.category).exclude(pk=pk)[:4]
    
    context = {
        'product': product,
        'related_products': related_products
    }
    return render(request, 'homepage/product_detail.html', context)


@login_required
def view_cart(request):
    """Display user's cart"""
    cart, created = Cart.objects.get_or_create(user=request.user)
    context = {
        'cart': cart
    }
    return render(request, 'homepage/cart.html', context)


@login_required
@require_POST
def add_to_cart(request, pk):
    """Add product to cart"""
    product = get_object_or_404(Product, pk=pk)
    quantity = int(request.POST.get('quantity', 1))
    
    if not product.is_in_stock or quantity > product.stock:
        messages.error(request, 'Not enough stock available')
        return redirect('product_detail', pk=pk)
    
    cart, created = Cart.objects.get_or_create(user=request.user)
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={'quantity': quantity}
    )
    
    if not created:
        if cart_item.quantity + quantity <= product.stock:
            cart_item.quantity += quantity
            cart_item.save()
        else:
            messages.error(request, 'Not enough stock available')
            return redirect('product_detail', pk=pk)
    
    messages.success(request, f'{product.name} added to cart!')
    return redirect('view_cart')


@login_required
@require_POST
def remove_from_cart(request, item_id):
    """Remove item from cart"""
    cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    cart_item.delete()
    messages.success(request, 'Item removed from cart')
    return redirect('view_cart')


@login_required
@require_POST
def update_cart_quantity(request, item_id):
    """Update quantity of item in cart"""
    cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    quantity = int(request.POST.get('quantity', 1))
    
    if quantity > 0:
        if quantity <= cart_item.product.stock:
            cart_item.quantity = quantity
            cart_item.save()
            messages.success(request, 'Cart updated')
        else:
            messages.error(request, 'Not enough stock available')
    else:
        cart_item.delete()
    
    return redirect('view_cart')


@login_required
def checkout(request):
    """Handle checkout process"""
    cart = get_object_or_404(Cart, user=request.user)
    
    if not cart.items.exists():
        messages.error(request, 'Your cart is empty')
        return redirect('shop')
    
    if request.method == 'POST':
        # Validate cart items still have stock
        for item in cart.items.all():
            if item.quantity > item.product.stock:
                messages.error(request, f'Not enough stock for {item.product.name}')
                return redirect('view_cart')
        
        # Create order
        order_number = str(uuid.uuid4())[:8].upper()
        subtotal = cart.get_total()
        shipping_cost = 0  # Can be calculated based on address
        total = subtotal + shipping_cost
        
        order = Order.objects.create(
            user=request.user,
            order_number=order_number,
            full_name=request.POST.get('full_name'),
            email=request.POST.get('email'),
            phone=request.POST.get('phone'),
            address=request.POST.get('address'),
            city=request.POST.get('city'),
            postal_code=request.POST.get('postal_code'),
            country=request.POST.get('country'),
            subtotal=subtotal,
            shipping_cost=shipping_cost,
            total=total,
            status='pending'
        )
        
        # Create order items and update stock
        for cart_item in cart.items.all():
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                product_name=cart_item.product.name,
                product_price=cart_item.product.price,
                quantity=cart_item.quantity
            )
            # Update product stock
            cart_item.product.stock -= cart_item.quantity
            cart_item.product.save()
        
        # Clear cart
        cart.items.all().delete()
        
        messages.success(request, 'Order placed successfully!')
        return redirect('order_success', order_id=order.id)
    
    context = {
        'cart': cart
    }
    return render(request, 'homepage/checkout.html', context)


@login_required
def order_success(request, order_id):
    """Display order success page"""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    context = {
        'order': order
    }
    return render(request, 'homepage/order_success.html', context)


@login_required
def my_orders(request):
    """Display user's order history"""
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    context = {
        'orders': orders
    }
    return render(request, 'homepage/my_orders.html', context)


# ===== ADMIN VIEWS =====

@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    """Admin dashboard with statistics"""
    total_products = Product.objects.count()
    total_orders = Order.objects.count()
    total_revenue = sum(order.total for order in Order.objects.all())
    pending_orders = Order.objects.filter(status='pending').count()
    
    recent_orders = Order.objects.all().order_by('-created_at')[:5]
    
    context = {
        'total_products': total_products,
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'pending_orders': pending_orders,
        'recent_orders': recent_orders
    }
    return render(request, 'homepage/admin_dashboard.html', context)


@login_required
@user_passes_test(is_admin)
def admin_products(request):
    """List all products for admin"""
    products = Product.objects.all().order_by('-created_at')
    context = {
        'products': products
    }
    return render(request, 'homepage/admin_products.html', context)


@login_required
@user_passes_test(is_admin)
def add_product(request):
    """Add new product"""
    categories = Category.objects.all()
    
    if request.method == 'POST':
        try:
            category = Category.objects.get(id=request.POST.get('category'))
            product = Product.objects.create(
                name=request.POST.get('name'),
                category=category,
                description=request.POST.get('description'),
                price=request.POST.get('price'),
                stock=request.POST.get('stock', 0),
                shape=request.POST.get('shape', 'round'),
                ingredients=request.POST.get('ingredients'),
                allergens=request.POST.get('allergens'),
                is_featured=request.POST.get('is_featured') == 'on'
            )
            
            if 'image' in request.FILES:
                product.image = request.FILES['image']
                product.save()
            
            messages.success(request, 'Product added successfully!')
            return redirect('admin_products')
        except Exception as e:
            messages.error(request, f'Error adding product: {str(e)}')
    
    context = {
        'categories': categories
    }
    return render(request, 'homepage/add_product.html', context)


@login_required
@user_passes_test(is_admin)
def edit_product(request, pk):
    """Edit existing product"""
    product = get_object_or_404(Product, pk=pk)
    categories = Category.objects.all()
    
    if request.method == 'POST':
        try:
            product.name = request.POST.get('name')
            product.category = Category.objects.get(id=request.POST.get('category'))
            product.description = request.POST.get('description')
            product.price = request.POST.get('price')
            product.stock = request.POST.get('stock', 0)
            product.shape = request.POST.get('shape', 'round')
            product.ingredients = request.POST.get('ingredients')
            product.allergens = request.POST.get('allergens')
            product.is_featured = request.POST.get('is_featured') == 'on'
            
            if 'image' in request.FILES:
                product.image = request.FILES['image']
            
            product.save()
            messages.success(request, 'Product updated successfully!')
            return redirect('admin_products')
        except Exception as e:
            messages.error(request, f'Error updating product: {str(e)}')
    
    context = {
        'product': product,
        'categories': categories
    }
    return render(request, 'homepage/edit_product.html', context)


@login_required
@user_passes_test(is_admin)
def delete_product(request, pk):
    """Delete a product"""
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        product.delete()
        messages.success(request, 'Product deleted successfully!')
        return redirect('admin_products')
    
    context = {
        'product': product
    }
    return render(request, 'homepage/delete_product.html', context)


@login_required
@user_passes_test(is_admin)
def admin_orders(request):
    """Manage orders"""
    orders = Order.objects.all().order_by('-created_at')
    
    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    context = {
        'orders': orders
    }
    return render(request, 'homepage/admin_orders.html', context)


@login_required
@user_passes_test(is_admin)
def update_order_status(request, order_id):
    """Update order status"""
    order = get_object_or_404(Order, id=order_id)
    
    if request.method == 'POST':
        status = request.POST.get('status')
        if status in dict(Order._meta.get_field('status').choices):
            order.status = status
            order.save()
            messages.success(request, 'Order status updated!')
    
    return redirect('admin_orders')


# Authentication views
def register(request):
    """User registration"""
    if request.method == 'POST':
        from django.contrib.auth.models import User
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        
        if password != password_confirm:
            messages.error(request, 'Passwords do not match')
            return redirect('register')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists')
            return redirect('register')
        
        user = User.objects.create_user(username=username, email=email, password=password)
        Cart.objects.create(user=user)
        messages.success(request, 'Account created successfully! Please log in.')
        return redirect('login')
    
    return render(request, 'homepage/register.html')


def user_login(request):
    """User login"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')
            next_page = request.GET.get('next', 'home')
            return redirect(next_page)
        else:
            messages.error(request, 'Invalid username or password')
    
    return render(request, 'homepage/login.html')


def user_logout(request):
    """User logout"""
    logout(request)
    messages.success(request, 'You have been logged out')
    return redirect('home')

