from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import psycopg2
import psycopg2.extras
import urllib.parse as urlparse
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'super-secret'

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Conectare la baza de date
url = urlparse.urlparse(os.getenv("DATABASE_URL"))

db = psycopg2.connect(
    database=url.path[1:],
    user=url.username,
    password=url.password,
    host=url.hostname,
    port=url.port
)

@app.route('/')
def home():
    return render_template('home.html')


@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    parola = request.form['parola']

    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()

    if user and check_password_hash(user['password'], parola):
        session['email'] = email
        return redirect(url_for('dashboard'))
    else:
        return render_template('login.html', error="Email sau parolă greșite.")

@app.route('/dashboard')
def dashboard():
    if 'email' in session:
        email = session['email']
        cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Date angajat
        cursor.execute("SELECT nume, functie FROM users WHERE email = %s", (email,))

        user = cursor.fetchone()
        if not user:
            return redirect(url_for('logout'))
        nume = user['nume']
        functie = user['functie']


        # Consimțăminte acordate
        cursor.execute("SELECT COUNT(*) AS total FROM consimtamant_extins WHERE email = %s AND status = 'acordat'", (email,))
        acordate = cursor.fetchone()['total']

        # Consimțăminte retrase
        cursor.execute("SELECT COUNT(*) AS total FROM consimtamant_extins WHERE email = %s AND status = 'retras'", (email,))
        retrase = cursor.fetchone()['total']

        return render_template(
            'dashboard_angajat.html',
            email=email,
            nume=nume,
            functie=functie,
            acordate=acordate,
            retrase=retrase
        )
    else:
        return redirect(url_for('home'))



@app.route('/salveaza_consimtamant', methods=['POST'])
def salveaza_consimtamant():
    if 'email' not in session:
        return redirect(url_for('home'))

    email = session['email']
    status = 'acordat' if request.form.get('consimtamant') else 'neacordat'
    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent')

    cursor = db.cursor()
    query = """
        INSERT INTO consimtamant_extins (
            email, status, scop, tip_consimtamant, data_acordarii,
            ip, user_agent, locatie, pagina_origine, rol, departament
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    values = (
        email, status, 'abonare_newsletter', 'explicit', datetime.now(),
        ip, user_agent, 'RO', 'https://platforma.ro/formular', 'angajat', 'Resurse Umane'
    )

    cursor.execute(query, values)
    db.commit()

    session['succes'] = "Consimțământul a fost salvat cu succes ✅"
    return redirect(url_for('dashboard'))

@app.route('/consimtamant')
def consimtamant():
    if 'email' not in session:
        return redirect(url_for('home'))

    email = session['email']
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT id, status, scop, data_acordarii, ip, locatie, '' AS document_url
        FROM consimtamant_extins
        WHERE email = %s
        ORDER BY data_acordarii DESC
    """, (email,))
    
    consimtaminte = cursor.fetchall()

    return render_template('consimtamant.html', email=email, consimtaminte=consimtaminte)
@app.route('/acorda_consimtamant')
def acorda_consimtamant():
    if 'email' not in session:
        return redirect(url_for('home'))

    email = session['email']
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Preluăm ultimul document încărcat
    cursor.execute("SELECT cale_fisier FROM documente ORDER BY id DESC LIMIT 1")
    rezultat = cursor.fetchone()

    if rezultat:
        document_url = '/' + rezultat['cale_fisier']
    else:
        document_url = None

    return render_template('acorda_consimtamant.html', email=email, document_url=document_url)


@app.route('/modifica_status', methods=['POST'])
def modifica_status():
    if 'email' not in session:
        return redirect(url_for('home'))

    id_consimtamant = request.form['id']
    status_nou = request.form['status']

    cursor = db.cursor()
    cursor.execute("UPDATE consimtamant_extins SET status = %s WHERE id = %s", (status_nou, id_consimtamant))
    db.commit()

    return redirect(url_for('consimtamant'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# 🔐 Login admin
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    error = None

    if request.method == 'POST':
        email = request.form['email']
        parola = request.form['parola']

        cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT * FROM admin_users WHERE email = %s", (email,))
        admin = cursor.fetchone()

        if admin and check_password_hash(admin['password'], parola):
            session['admin_email'] = email
            return redirect(url_for('admin_dashboard_full'))
        else:
            error = "Email sau parolă greșite."

    return render_template('admin_login.html', error=error)
@app.route('/admin_register', methods=['GET', 'POST'])
def admin_register():
    error = None
    mesaj = None

    if request.method == 'POST':
        email = request.form['email']
        parola = request.form['parola']
        confirmare = request.form['confirmare']

        if parola != confirmare:
            error = "Parolele nu coincid!"
        elif len(parola) < 8:
            error = "Parola trebuie să aibă cel puțin 8 caractere!"
        else:
            cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("SELECT * FROM admin_users WHERE email = %s", (email,))
            existent = cursor.fetchone()

            if existent:
                error = "Emailul este deja înregistrat!"
            else:
                parola_hash = generate_password_hash(parola)
                cursor.execute("INSERT INTO admin_users (email, password) VALUES (%s, %s)", (email, parola_hash))
                db.commit()
                mesaj = "Contul a fost creat cu succes! Acum te poți autentifica."
                return redirect(url_for('admin_login'))

    return render_template('admin_register.html', error=error, mesaj=mesaj)


@app.route('/admin_dashboard')
def admin_dashboard():
    if 'admin_email' not in session:
        return redirect(url_for('admin_login'))

    email_filter = request.args.get('email')
    status_filter = request.args.get('status')

    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query = """
        SELECT email, status, scop, tip_consimtamant, data_acordarii, ip, locatie, departament
        FROM consimtamant_extins
        WHERE 1=1
    """
    values = []

    if email_filter:
        query += " AND email LIKE %s"
        values.append(f"%{email_filter}%")

    if status_filter:
        query += " AND status = %s"
        values.append(status_filter)

    query += " ORDER BY data_acordarii DESC"

    cursor.execute(query, values)
    consimtaminte = cursor.fetchall()

    for c in consimtaminte:
        if c['status'] == 'neacordat':
            data = c['data_acordarii']
            if isinstance(data, datetime):
                c['expirat'] = (datetime.now() - data) > timedelta(days=30)
            else:
                c['expirat'] = False
        else:
            c['expirat'] = False

    expirate_count = sum(1 for c in consimtaminte if c.get('expirat'))

    return render_template(
        "admin_dashboard.html",
        consimtaminte=consimtaminte,
        admin_email=session['admin_email'],
        expirate_count=expirate_count
    )

@app.route('/upload_document', methods=['POST'])
def upload_document():
    if 'admin_email' not in session:
        return redirect(url_for('admin_login'))

    if 'document' not in request.files:
        session['upload_error'] = "Nu s‑a selectat niciun fișier."
        return redirect(url_for('admin_dashboard'))

    file = request.files['document']

    if file.filename == '':
        session['upload_error'] = "Nume de fișier invalid."
        return redirect(url_for('admin_dashboard'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO documente (nume_fisier, cale_fisier, scop) VALUES (%s, %s, %s)",
            (filename, filepath, 'utilizare_imagine_angajat')
        )
        db.commit()

        session['upload_succes'] = f"Fișierul „{filename}” a fost încărcat cu succes!"
        return redirect(url_for('admin_dashboard'))

    session['upload_error'] = "Fișier invalid! Trebuie să fie PDF sau DOCX."
    return redirect(url_for('admin_dashboard'))

@app.route('/admin_dashboard_full')
def admin_dashboard_full():
    if 'admin_email' not in session:
        return redirect(url_for('home'))

    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("SELECT COUNT(*) AS total FROM users")
    total_angajati = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM consimtamant_extins WHERE status = 'acordat'")
    acordate = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM consimtamant_extins WHERE status = 'retras'")
    retrase = cursor.fetchone()['total']

    cursor.execute("SELECT MAX(data_acordarii) AS ultima FROM consimtamant_extins")
    ultima_modificare = cursor.fetchone()['ultima']

    return render_template(
        'admin_dashboard_full.html',
        total_angajati=total_angajati,
        acordate=acordate,
        retrase=retrase,
        ultima_modificare=ultima_modificare,
        admin_email=session['admin_email']
    )

@app.route('/admin_angajati', methods=['GET', 'POST'])
def admin_angajati():
    if 'admin_email' not in session:
        return redirect(url_for('home'))

    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if request.method == 'POST':
        nume = request.form['nume']
        email = request.form['email']
        functie = request.form['functie']
        parola = request.form['parola']
        rol = request.form['rol']  # 🆕 adăugat

        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        existent = cursor.fetchone()

        if not existent:
            parola_hash = generate_password_hash(parola)
            cursor.execute(
                "INSERT INTO users (nume, email, functie, password, role) VALUES (%s, %s, %s, %s, %s)",
                (nume, email, functie, parola_hash, rol)
            )
            db.commit()

    cursor.execute("SELECT nume, email, functie FROM users WHERE role = 'angajat'")
    angajati = cursor.fetchall()

    return render_template('admin_angajati.html', angajati=angajati, admin_email=session['admin_email'])



@app.route('/angajati')
def lista_angajati():
    if 'admin_email' not in session:
        return redirect(url_for('home'))

    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT id, nume, email, functie FROM users WHERE role = 'angajat'")
    angajati = cursor.fetchall()

    return render_template('angajati.html', angajati=angajati)

@app.route('/adauga_angajat', methods=['GET', 'POST'])
def adauga_angajat():
    if 'admin_email' not in session:
        return redirect(url_for('home'))

    mesaj = None
    eroare = None

    if request.method == 'POST':
        nume = request.form['nume']
        email = request.form['email']
        functie = request.form['functie']
        parola = request.form['parola']

        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        existent = cursor.fetchone()

        if existent:
            eroare = "Emailul este deja folosit."
        else:
            parola_hash = generate_password_hash(parola)
            cursor.execute("""
                INSERT INTO users (nume, email, functie, password, role)
                VALUES (%s, %s, %s, %s, 'angajat')
            """, (nume, email, functie, parola_hash))
            db.commit()
            mesaj = "Angajat adăugat cu succes!"

    return render_template('adauga_angajat.html', mesaj=mesaj, eroare=eroare)


@app.route('/api/consimtamant/<email>', methods=['GET'])
def get_consimtamant(email):
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT status, data_acordarii FROM consimtamant_extins WHERE email = %s ORDER BY data_acordarii DESC LIMIT 1", (email,))
    rezultat = cursor.fetchone()

    if rezultat:
        return jsonify({
            "email": email,
            "status": rezultat['status'],
            "data_acordarii": str(rezultat['data_acordarii'])
        })
    else:
        return jsonify({
            "email": email,
            "status": "necunoscut",
            "mesaj": "Nu există consimțământ salvat pentru acest utilizator."
        }), 404

