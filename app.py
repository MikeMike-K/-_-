import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'my-secret-key-123'
# Используем PostgreSQL с Render, если переменная окружения есть, иначе SQLite для локальной работы
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    # Render иногда дает ссылку с postgres://, а SQLAlchemy требует postgresql://
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///school.db'
app.config['UPLOAD_FOLDER'] = 'uploads'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)


# --- МОДЕЛИ ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='student')  # 'student' или 'teacher'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class FileItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    original_name = db.Column(db.String(200), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Связь с пользователем, чтобы знать кто загрузил
    uploader = db.relationship('User', backref=db.backref('files', lazy=True))


# --- ЗАЩИТА МАРШРУТОВ ---
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Сначала войдите в систему!', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def teacher_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if user.role != 'teacher':
            flash('Доступно только для учителей!', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)

    return decorated_function


# --- МАРШРУТЫ ---

@app.route('/')
@login_required
def index():
    user = User.query.get(session['user_id'])
    files = FileItem.query.all()
    return render_template('index.html', user=user, files=files)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            session['role'] = user.role
            flash(f'Добро пожаловать, {user.username}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверный логин или пароль', 'danger')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует', 'danger')
            return redirect(url_for('register'))

        new_user = User(username=username, role=role)
        new_user.set_password(password)

        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Регистрация успешна! Теперь войдите.', 'success')
            return redirect(url_for('login'))
        except:
            db.session.rollback()
            flash('Ошибка при регистрации', 'danger')

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/upload', methods=['POST'])
@teacher_required
def upload_file():
    if 'file' not in request.files:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('index'))

    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('index'))

    if file:
        filename = secure_filename(file.filename)
        unique_name = f"{os.urandom(8).hex()}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))

        new_file = FileItem(
            filename=unique_name,
            original_name=filename,
            uploaded_by=session['user_id']
        )
        db.session.add(new_file)
        db.session.commit()
        flash('Файл успешно загружен!', 'success')

    return redirect(url_for('index'))


@app.route('/delete/<int:file_id>')
@teacher_required
def delete_file(file_id):
    file_item = FileItem.query.get_or_404(file_id)
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], file_item.filename))
    except:
        pass  # Если файла нет на диске, просто удаляем из БД

    db.session.delete(file_item)
    db.session.commit()
    flash('Файл удален', 'info')
    return redirect(url_for('index'))


@app.route('/download/<int:file_id>')
@login_required
def download_file(file_id):
    file_item = FileItem.query.get_or_404(file_id)
    return send_from_directory(app.config['UPLOAD_FOLDER'], file_item.filename, as_attachment=True,
                               download_name=file_item.original_name)

with app.app_context():
    db.create_all()

if __name__ == '__main__':


    # Render предоставляет порт через переменную окружения PORT
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)