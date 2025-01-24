import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    stocks = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0",
                        user_id=session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]
    total_value = cash
    for stock in stocks:
        quote = lookup(stock["symbol"])
        stock["symbol"] = quote["symbol"]
        stock["price"] = quote["price"]
        stock["value"] = stock["price"] * stock["total_shares"]
        total_value += stock["value"]
    return render_template("index.html", stocks=stocks, cash=cash, total_value=total_value)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol:
            return apology("must provide symbol")
        if not shares:
            return apology("must provide shares")
        if not shares.isdigit():
            return apology("num of shares not valid")
        if int(shares) <= 0:
            return apology("num of shares not valid")

        query = lookup(symbol)

        if not query:
            return apology("Symbol not found")
        price = query["price"]
        total_price = int(shares) * price
        cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]

        if cash < total_price:
            return apology("Not enough cash to complete the purchase")

        db.execute("UPDATE users SET cash = cash - :total_price WHERE id = :user_id",
                   total_price=total_price, user_id=session["user_id"])

        db.execute("INSERT INTO transactions (user_id, shares, price, symbol) VALUES (:user_id, :shares, :price, :symbol)",
                   user_id=session["user_id"], shares=shares, price=price, symbol=symbol)
        flash(f"bought")
        return redirect("/")

    return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # get the info from the database
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = :user_id ORDER BY time DESC",
                              user_id=session["user_id"])
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        # Ensure Symbol is exists
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("ENTER A SYMBOL", 400)
        query = lookup(symbol)
        if not query:
            return apology("INVALID SYMBOL", 400)
        return render_template("quote.html", query=query)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        if not (username := request.form.get("username")):
            return apology("MISSING USERNAME")

        if not (password := request.form.get("password")):
            return apology("MISSING PASSWORD")

        if not (confirmation := request.form.get("confirmation")):
            return apology("PASSWORD DON'T MATCH")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?;", username)

        # Ensure username not in database
        if len(rows) != 0:
            return apology(f"The username '{username}' already exists. Please choose another name.")

        # Ensure first password and second password are matched
        if password != confirmation:
            return apology("password not matched")

        # Insert username into database
        id = db.execute("INSERT INTO users (username, hash) VALUES (?, ?);",
                        username, generate_password_hash(password))

        # Remember which user has logged in
        session["user_id"] = id

        flash("Registered!")

        return redirect("/")
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # get the stock
    stocks = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0",
                        user_id = session["user_id"])
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        if not symbol:
            return apology("symbol not found")
        elif not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("must provide a positive number")
        else:
            shares = int(shares)

        for stock in stocks:
            if stock["symbol"] == symbol:
                if stock["total_shares"] < shares:
                    return apology("not enough shares")
                else:
                    # get quote
                    quote = lookup(symbol)
                    if quote is None:
                        return apology("symbol not found")
                    price = quote["price"]
                    total_sale = shares * price
                    # update the use table
                    db.execute("UPDATE users SET cash = cash + :total_sale WHERE id = :user_id",
                               total_sale=total_sale, user_id=session["user_id"])
                    # add the sell to the history table
                    db.execute("INSERT INTO transactions (user_id, shares, price, symbol) VALUES (:user_id, :shares, :price, :symbol)",
                               user_id=session["user_id"], shares=-shares, price=price, symbol=symbol)
                    flash(f"sold")
                    return redirect("/")
        return apology("symbol not found")
    else:
        return render_template("sell.html", stocks=stocks)


@app.route("/add_cash", methods=["GET", "POST"])
@login_required
def add_cash():
    #add cash to the user_account

    if request.method == "POST":
        # get amount of cash to add from form
        money = request.form.get("cash")
        if not money:
            return apology("enter a cash")
        elif not money.isdigit():
            return apology("enter a cash")
        elif int(money) <= 0:
            return apology("enter a cash")
        else:
            db.execute("SELECT cash FROM users WHERE id = :user_id",
                       user_id=session["user_id"])[0]["cash"]
            db.execute("UPDATE users SET cash = cash + :money WHERE id = :user_id",
                       money=money, user_id=session["user_id"])
        flash("Cash added successfully")
        return redirect("/")
    return render_template("add.html")








