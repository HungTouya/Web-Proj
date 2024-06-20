import mysql.connector
from mysql.connector import errorcode
from flask import Flask, request, redirect, url_for, render_template, session
from decimal import Decimal
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with your secret key for session management

# MySQL database configuration
db_config = {
    'user': 'root',             # Replace with your MySQL username
    'password': 'Kobukovu2003@',# Replace with your MySQL password
    'host': '127.0.0.1',        # Replace with your MySQL host (e.g., 'localhost')
    'database': 'foodweb',      # Ensure this matches your database name
    'connection_timeout': 300   # Adjust timeout value as per your server settings
}

def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
    except mysql.connector.Error as err:
        if err.errno == errorcode.CR_SERVER_GONE_ERROR:
            # Reconnect if server has gone away
            conn = mysql.connector.connect(**db_config)
        else:
            raise  # Raise the error if it's not CR_SERVER_GONE_ERROR
    return conn

@app.route('/')
def home():
    if 'username' in session:
        return render_template('home.html')
    else:
        return redirect(url_for('login'))
    
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user is None or not check_password_hash(user[0], password):
            return render_template('login.html', message="Invalid username or password. <a href='/register'>Register here</a>.")
        
        session['username'] = username  # Store username in session
        return redirect(url_for('home'))
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        retype_password = request.form['retype_password']
        
        if password != retype_password:
            return render_template('register.html', message="Passwords do not match, please try again.")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        
        if user:
            conn.close()
            return render_template('register.html', message="Username already taken, please choose another.")
        
        hashed_password = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_password))
        conn.commit()
        conn.close()
        
        session['username'] = username  # Store username in session after registration
        return redirect(url_for('home'))
    
    return render_template('register.html')


@app.route('/logout', methods=['POST'])
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))


@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query')
    
    if not query:
        return render_template('search.html')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    sql_query = "SELECT * FROM food WHERE name LIKE %s"
    cursor.execute(sql_query, ('%' + query + '%',))
    foods = cursor.fetchall()
    conn.close()
    
    if not foods:
        return "Food not found."
    
    return render_template('search_results.html', foods=foods)

@app.route('/food/<food_name>.html')
def food_page(food_name):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, price, restaurant_name FROM food WHERE LOWER(REPLACE(name, ' ', '')) = %s", (food_name,))
    food_info = cursor.fetchone()
    conn.close()
    
    if food_info:
        return render_template(f'{food_name}.html', food_id=food_info['id'], price=food_info['price'], restaurant=food_info['restaurant_name'])
    else:
        return "Food not found."

@app.route('/order')
def order():
    if 'username' in session:
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # Fetch the most recent order date for the logged-in user
            cursor.execute("""
                SELECT MAX(order_date) as latest_order_date
                FROM orders 
                WHERE user_id = (
                    SELECT id FROM users WHERE username = %s
                )
            """, (session['username'],))
            result = cursor.fetchone()
            latest_order_date = result['latest_order_date'] if result else None

            if latest_order_date:
                # Fetch the orders made on the most recent order date
                cursor.execute("""
                    SELECT f.name AS food_name, f.price, f.restaurant_name, o.order_date, COUNT(o.id) as quantity
                    FROM orders o 
                    JOIN food f ON o.food_id = f.id 
                    WHERE o.user_id = (
                        SELECT id FROM users WHERE username = %s
                    )
                    AND o.order_date = %s
                    GROUP BY f.name, f.price, f.restaurant_name, o.order_date
                """, (session['username'], latest_order_date))
                orders = cursor.fetchall()
                conn.close()

                if orders:
                    total_price = sum(order['price'] * order['quantity'] for order in orders)
                    return render_template('order.html', orders=orders, total_price=total_price)
                else:
                    return render_template('order.html', orders=[], total_price=0.0)
            else:
                return render_template('order.html', orders=[], total_price=0.0)
        
        except Exception as e:
            print(f"Error fetching orders: {str(e)}")
            return "Error fetching orders. Please try again later."
    
    else:
        return redirect(url_for('login'))



@app.route('/cart')
def cart():
    cart_items = session.get('cart_items', [])
    total_price = sum(item['price'] for item in cart_items)
    
    return render_template('cart.html', cart_items=cart_items, total_price=total_price)

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if request.method == 'POST':
        food_id = request.form['food_id']
        quantity = int(request.form['quantity'])

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name, price, restaurant_name FROM food WHERE id = %s", (food_id,))
        food = cursor.fetchone()

        if not food:
            return "Food not found."

        # Convert price to float if necessary
        if isinstance(food['price'], Decimal):
            food['price'] = float(food['price'])
        elif isinstance(food['price'], str):
            food['price'] = float(food['price'].replace(',', ''))  # Handle commas in price

        if 'cart_items' not in session:
            session['cart_items'] = []
            session['total_price'] = 0.0

        # Check if the item is already in the cart
        for item in session['cart_items']:
            if item['id'] == food_id:
                item['quantity'] += quantity
                session['total_price'] += food['price'] * quantity
                session.modified = True
                conn.close()
                return redirect(url_for('cart'))

        # Add new item to cart
        food['quantity'] = quantity
        session['cart_items'].append(food)
        session['total_price'] += food['price'] * quantity

        session.modified = True
        conn.close()

        return redirect(url_for('cart'))

    return render_template('cart.html', cart_items=session.get('cart_items', []), total_price=session.get('total_price', 0.0))


@app.route('/remove_from_cart/<int:food_id>', methods=['POST'])
def remove_from_cart(food_id):
    if request.method == 'POST':
        if 'cart_items' in session:
            session['cart_items'] = [item for item in session['cart_items'] if item['id'] != food_id]
            
            total_price = sum(item['price'] for item in session['cart_items'])
            session['total_price'] = total_price
            
            session.modified = True
    
    return redirect(url_for('cart'))



@app.route('/user')
def user():
    return render_template('user.html')
@app.route('/buy_now', methods=['POST'])
def buy_now():
    if 'username' in session:  # Check if user is logged in
        username = session['username']
        user_id = get_user_id(username)  # Function to retrieve user_id based on username

        if 'cart_items' in session and session['cart_items']:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()

                for item in session['cart_items']:
                    food_id = item['id']
                    quantity = item['quantity']
                    for _ in range(quantity):
                        cursor.execute("INSERT INTO orders (user_id, food_id) VALUES (%s, %s)", (user_id, food_id))

                conn.commit()
                conn.close()

                # Clear cart after purchase
                session.pop('cart_items', None)
                session['total_price'] = 0.0

                # Redirect to order page after successful purchase
                return redirect(url_for('order'))

            except Exception as e:
                conn.rollback()
                conn.close()
                print(f"Error processing order: {str(e)}")
                return f"Error processing order: {str(e)}"

        else:
            return "Your cart is empty."

    else:
        return "User not logged in. Please log in to place an order."


def get_user_id(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return user[0]
    else:
        return None
    
@app.route('/confirm_payment', methods=['POST'])
def confirm_payment():
    if 'username' in session:
        # Handle payment confirmation logic here
        payment_method = request.form.get('payment_method')

        # Perform any additional processing based on the payment method chosen

        # Redirect to thank you page
        return redirect(url_for('thankyou'))
    
    else:
        return "User not logged in. Please log in to confirm payment."

@app.route('/thankyou')
def thankyou():
    return render_template('thankyou.html')

@app.route('/history')
def history():
    if 'username' in session:
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Fetch all orders for the logged-in user
            cursor.execute("""
                SELECT f.name AS food_name, f.price, f.restaurant_name, o.order_date, COUNT(o.id) as quantity
                FROM orders o 
                JOIN food f ON o.food_id = f.id 
                WHERE o.user_id = (
                    SELECT id FROM users WHERE username = %s
                )
                GROUP BY f.name, f.price, f.restaurant_name, o.order_date
                ORDER BY o.order_date DESC
            """, (session['username'],))
            orders = cursor.fetchall()
            conn.close()

            return render_template('history.html', orders=orders)
        
        except Exception as e:
            print(f"Error fetching purchase history: {str(e)}")
            return "Error fetching purchase history. Please try again later."
    
    else:
        return redirect(url_for('login'))


@app.route('/bunbo.html')
def bunbo():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, price, restaurant_name FROM food WHERE name = 'Bun bo'")
    food_info = cursor.fetchone()
    conn.close()
    
    if food_info:
        return render_template('bunbo.html', food_id=food_info['id'], price=food_info['price'], restaurant=food_info['restaurant_name'])
    else:
        return "Food not found."

@app.route('/comtam.html')
def comtam():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, price, restaurant_name FROM food WHERE name = 'Com tam'")
    food_info = cursor.fetchone()
    conn.close()
    
    if food_info:
        return render_template('comtam.html', food_id=food_info['id'], price=food_info['price'], restaurant=food_info['restaurant_name'])
    else:
        return "Food not found."

@app.route('/chaolong.html')
def chaolong():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, price, restaurant_name FROM food WHERE name = 'Chaolong'")
    food_info = cursor.fetchone()

    conn.close()

    if food_info:
        return render_template('chaolong.html', food_id=food_info['id'], price=food_info['price'], restaurant=food_info['restaurant_name'])
    else:
        return "Food not found."

@app.route('/banhmi.html')
def banhmi():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, price, restaurant_name FROM food WHERE name = 'Banh mi'")
    food_info = cursor.fetchone()

    conn.close()

    if food_info:
        return render_template('banhmi.html', food_id=food_info['id'], price=food_info['price'], restaurant=food_info['restaurant_name'])
    else:
        return "Food not found."
    
@app.route('/xoiman.html')
def xoiman():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, price, restaurant_name FROM food WHERE name = 'Xoiman'")
    food_info = cursor.fetchone()

    conn.close()

    if food_info:
        return render_template('xoiman.html', food_id=food_info['id'], price=food_info['price'], restaurant=food_info['restaurant_name'])
    else:
        return "Food not found." 
    
@app.route('/trasua.html')
def trasua():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, price, restaurant_name FROM food WHERE name = 'Tra sua'")
    food_info = cursor.fetchone()

    conn.close()

    if food_info:
        return render_template('trasua.html', food_id=food_info['id'], price=food_info['price'], restaurant=food_info['restaurant_name'])
    else:
        return "Food not found."

if __name__ == '__main__':
    app.run(debug=True)
