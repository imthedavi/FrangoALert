from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai
from datetime import datetime
import json
import os

# --- CONFIG ENV ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY não definida")

if not SECRET_KEY:
    raise ValueError("SECRET_KEY não definida")

# --- APP ---
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fakealert.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- IA CLIENT (instancia única) ---
client = genai.Client(api_key=GEMINI_API_KEY)

# --- TABELAS ---
post_likes = db.Table('post_likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'))
)

post_saves = db.Table('post_saves',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'))
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)

    liked_posts = db.relationship('Post', secondary=post_likes, backref=db.backref('liked_by', lazy='dynamic'))
    saved_posts = db.relationship('Post', secondary=post_saves, backref=db.backref('saved_by', lazy='dynamic'))

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500))
    category = db.Column(db.String(50), default='Geral')
    verified = db.Column(db.Boolean, default=True)
    author = db.Column(db.String(100), default='Redação')
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- ROTAS ---
@app.route('/')
def index():
    search_query = request.args.get('q')
    category_filter = request.args.get('cat')

    query = Post.query

    if category_filter and category_filter != 'Feed':
        query = query.filter_by(category=category_filter)

    if search_query:
        query = query.filter(
            Post.title.contains(search_query) |
            Post.content.contains(search_query)
        )

    posts = query.order_by(Post.date_posted.desc()).all()
    return render_template('index.html', posts=posts)

# --- LOGIN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))

        flash('Credenciais inválidas.', 'danger')

    return render_template('login.html', mode=request.args.get('mode'))

# --- REGISTER ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        admin_code = request.form.get('admin_code')

        if User.query.filter_by(email=email).first():
            flash('Email já cadastrado.', 'warning')
            return redirect(url_for('login'))

        new_user = User(
            username=name,
            email=email,
            password=generate_password_hash(password),
            is_admin=(admin_code == 'admin123')
        )

        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        return redirect(url_for('index'))

    return redirect(url_for('login', mode='register'))

# --- LOGOUT ---
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', tab=request.args.get('tab', 'saved'))

# --- AÇÕES ---
@app.route('/like/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    post = db.session.get(Post, post_id)

    if post in current_user.liked_posts:
        current_user.liked_posts.remove(post)
        liked = False
    else:
        current_user.liked_posts.append(post)
        liked = True

    db.session.commit()
    return jsonify({'liked': liked, 'count': post.liked_by.count()})

@app.route('/save/<int:post_id>', methods=['POST'])
@login_required
def save_post(post_id):
    post = db.session.get(Post, post_id)

    if post in current_user.saved_posts:
        current_user.saved_posts.remove(post)
        saved = False
    else:
        current_user.saved_posts.append(post)
        saved = True

    db.session.commit()
    return jsonify({'saved': saved})

# --- ADMIN ---
@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    posts = Post.query.order_by(Post.date_posted.desc()).all()
    return render_template('admin.html', posts=posts)

# --- IA ---
def call_gemini(prompt):
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return {"text": response.text}
    except Exception as e:
        return {"error": str(e)}

@app.route('/api/verify_fact', methods=['POST'])
@login_required
def verify_fact():
    prompt = f"Analise a veracidade em PT-BR (max 20 palavras): {request.json.get('title')} - {request.json.get('content')}"
    result = call_gemini(prompt)

    if "error" in result:
        return jsonify(result), 500

    return jsonify(result)

@app.route('/api/generate_content', methods=['POST'])
@login_required
def generate_content():
    topic = request.json.get('topic')

    prompt = (
        f"Gere uma notícia sobre '{topic}' e retorne JSON: "
        f"{{\"title\": \"...\", \"content\": \"...\", \"verified\": true/false}}"
    )

    result = call_gemini(prompt)

    if "error" in result:
        return jsonify(result), 500

    try:
        clean = result["text"].replace('```json', '').replace('```', '').strip()
        data = json.loads(clean)
        return jsonify(data)
    except:
        return jsonify({"error": "Erro ao processar resposta"}), 500

# --- RUN ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    app.run(debug=True)