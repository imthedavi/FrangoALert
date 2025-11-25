from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import json
import re
import google.generativeai as genai

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chave-secreta-dev-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fakealert.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- CONFIGURAÇÃO DA IA ---
GEMINI_API_KEY = "Key do gemini".strip()

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# TABELAS
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
    password = db.Column(db.String(100))
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

# ROTAS
@app.route('/')
def index():
    search_query = request.args.get('q')
    category_filter = request.args.get('cat')
    query = Post.query
    if category_filter and category_filter != 'Feed': query = query.filter_by(category=category_filter)
    if search_query: query = query.filter(Post.title.contains(search_query) | Post.content.contains(search_query))
    posts = query.order_by(Post.date_posted.desc()).all()
    return render_template('index.html', posts=posts)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if not user and email == 'admin' and password == '1234':
            user = User(username='Admin', email='admin', password='1234', is_admin=True)
            db.session.add(user)
            db.session.commit()
        if user and user.password == password:
            login_user(user)
            return redirect(url_for('index'))
        flash('Credenciais inválidas.', 'danger')
    return render_template('login.html', mode=request.args.get('mode'))

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
        new_user = User(username=name, email=email, password=password, is_admin=(admin_code == 'admin123'))
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('index'))
    return redirect(url_for('login', mode='register'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', tab=request.args.get('tab', 'saved'))

# AÇÕES AJAX
@app.route('/like/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    post = db.session.get(Post, post_id)
    liked = False
    if post in current_user.liked_posts: current_user.liked_posts.remove(post)
    else:
        current_user.liked_posts.append(post)
        liked = True
    db.session.commit()
    return jsonify({'liked': liked, 'count': post.liked_by.count()})

@app.route('/save/<int:post_id>', methods=['POST'])
@login_required
def save_post(post_id):
    post = db.session.get(Post, post_id)
    saved = False
    if post in current_user.saved_posts: current_user.saved_posts.remove(post)
    else:
        current_user.saved_posts.append(post)
        saved = True
    db.session.commit()
    return jsonify({'saved': saved})

# ADMIN
@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin: return redirect(url_for('index'))
    posts = Post.query.order_by(Post.date_posted.desc()).all()
    return render_template('admin.html', posts=posts)

@app.route('/post/form', methods=['GET', 'POST'])
@app.route('/post/form/<int:post_id>', methods=['GET', 'POST'])
@login_required
def post_form(post_id=None):
    if not current_user.is_admin: return redirect(url_for('index'))
    post = db.session.get(Post, post_id) if post_id else None
    if request.method == 'POST':
        data = {
            'title': request.form.get('title'), 'content': request.form.get('content'),
            'image_url': request.form.get('image_url'), 'category': request.form.get('category'),
            'author': request.form.get('author'), 'verified': request.form.get('verified') == '1'
        }
        if post:
            for k, v in data.items(): setattr(post, k, v)
        else: db.session.add(Post(**data))
        db.session.commit()
        return redirect(url_for('admin_dashboard'))
    return render_template('post_form.html', post=post)

@app.route('/post/delete/<int:post_id>')
@login_required
def delete_post(post_id):
    if not current_user.is_admin: return redirect(url_for('index'))
    post = db.session.get(Post, post_id)
    db.session.delete(post)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

# --- INTEGRAÇÃO GOOGLE AI ---

def call_gemini(prompt):
    if not GEMINI_API_KEY or "SUA_CHAVE" in GEMINI_API_KEY:
        return {"error": "Chave API não configurada no app.py"}

    try:
        # Usando modelo 2.5-flash
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        return {"text": response.text}
    except Exception as e:
        print(f"Erro IA: {e}")
        return {"error": f"Erro na IA: {str(e)}. Veja o terminal."}

@app.route('/api/verify_fact', methods=['POST'])
def verify_fact():
    prompt = f"Analise a veracidade em PT-BR (max 20 palavras) de forma direta e objetiva: {request.json.get('title')} - {request.json.get('content')}"
    result = call_gemini(prompt)
    
    if "error" in result:
        return jsonify({"result": "Erro API", "text": result["error"]})
        
    return jsonify({"result": "Análise IA", "text": result["text"]})

@app.route('/api/generate_content', methods=['POST'])
@login_required
def generate_content():
    topic = request.json.get('topic')
    
    # PROMPT ATUALIZADO PARA RETORNAR 'verified'
    prompt = (
        f"Atue como um editor sênior do site 'FakeAlert'. O usuário quer uma notícia atualizada sobre: '{topic}'. "
        f"Sua tarefa: Gere uma manchete e um texto curto sobre esse tema. "
        f"IMPORTANTE: Você deve decidir se vai criar um FATO REAL ou uma FAKE NEWS conhecida sobre o tema. "
        f"Retorne APENAS um JSON válido neste formato: "
        f"{{\"title\": \"...\", \"content\": \"...\", \"verified\": true/false}} "
        f"(Use true para Fato, false para Fake)"
    )
    
    result = call_gemini(prompt)
    
    if "error" in result:
        return jsonify({"error": result["error"]}), 500

    try:
        clean_text = result["text"].replace('```json', '').replace('```', '').strip()
        data = json.loads(clean_text)
        return jsonify(data)
    except:
        return jsonify({"error": "Erro ao processar resposta da IA"}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)