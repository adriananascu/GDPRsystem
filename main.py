from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask import Flask, render_template, request, redirect, url_for, session, flash

from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import psycopg2
import psycopg2.extras
import urllib.parse as urlparse
import os
from dotenv import load_dotenv
from flask import send_from_directory
from werkzeug.utils import secure_filename
from flask import send_file
import openpyxl
from io import BytesIO

load_dotenv()


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

@app.route('/login', methods=['GET'])
def login_get():
    return render_template('login.html')

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

        # Consimțăminte expirate (neacordate de peste 30 zile)
        cursor.execute("""
            SELECT data_acordarii FROM consimtamant_extins
            WHERE email = %s AND status = 'neacordat'
        """, (email,))
        neacordate = cursor.fetchall()

        expirate = 0
        for row in neacordate:
            if row['data_acordarii'] and (datetime.now() - row['data_acordarii']) > timedelta(days=30):
                expirate += 1

        return render_template(
            'dashboard_angajat.html',
            email=email,
            nume=nume,
            functie=functie,
            acordate=acordate,
            retrase=retrase,
            expirate=expirate
        )
    else:
        return redirect(url_for('home'))



@app.route('/setari')
def setari():
    if 'email' not in session:
        return redirect(url_for('login'))

    return render_template("setari.html", email=session['email'])


@app.route('/schimba_parola', methods=['GET', 'POST'])
def schimba_parola():
    if 'email' not in session:
        return redirect(url_for('login'))

    mesaj = None
    eroare = None

    if request.method == 'POST':
        veche = request.form['parola_veche']
        noua = request.form['parola_noua']
        confirmare = request.form['parola_confirmare']

        cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT password FROM users WHERE email = %s", (session['email'],))
        user = cursor.fetchone()

        if not user or not check_password_hash(user['password'], veche):
            eroare = "Parola veche este incorectă!"
        elif noua != confirmare:
            eroare = "Parolele noi nu coincid!"
        elif len(noua) < 8:
            eroare = "Parola nouă trebuie să aibă cel puțin 8 caractere!"
        else:
            parola_hash = generate_password_hash(noua)
            cursor.execute("UPDATE users SET password = %s WHERE email = %s", (parola_hash, session['email']))
            db.commit()
            mesaj = "Parola a fost schimbată cu succes!"

    return render_template("schimba_parola.html", mesaj=mesaj, eroare=eroare)

@app.route('/sterge_cont', methods=['GET', 'POST'])
def sterge_cont():
    if 'email' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        email = session['email']

        cursor = db.cursor()

        # Șterge consimțăminte legate de utilizator
        cursor.execute("DELETE FROM consimtamant_extins WHERE email = %s", (email,))

        # Șterge utilizatorul
        cursor.execute("DELETE FROM users WHERE email = %s", (email,))
        db.commit()

        session.clear()
        return redirect(url_for('home', mesaj='Contul a fost șters cu succes.'))

    return render_template('confirmare_stergere.html', email=session['email'])


@app.route('/salveaza_consimtamant', methods=['POST'])
def salveaza_consimtamant():
    if 'email' not in session:
        return redirect(url_for('home'))

    email = session['email']
    status = 'acordat' if 'consimtamant' in request.form else 'neacordat'
    tip_consimtamant = 'explicit'
    data_acordarii = datetime.now()
    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent')
    locatie = 'RO' 
    pagina_origine = request.referrer
    rol = 'angajat'
    departament = 'Resurse Umane' 
    scop = 'utilizare_imagine_angajat'

    # Obține ultimul document încărcat
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT id FROM documente ORDER BY id DESC LIMIT 1")
    document = cursor.fetchone()
    document_id = document['id'] if document else None

    if document_id is None:
        session['upload_error'] = "Nu există niciun document activ!"
        return redirect(url_for('dashboard'))

    # Salvează consimțământul
    cursor.execute("""
        INSERT INTO consimtamant_extins (
            email, status, scop, tip_consimtamant, data_acordarii,
            ip, user_agent, locatie, pagina_origine, rol, departament, document_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        email, status, scop, tip_consimtamant, data_acordarii,
        ip, user_agent, locatie, pagina_origine, rol, departament, document_id
    ))

    db.commit()
    return redirect(url_for('dashboard'))



@app.route('/consimtamant')
def consimtamant():
    if 'email' not in session:
        return redirect(url_for('home'))

    email = session['email']
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT DISTINCT ON (ce.document_id) 
            ce.id,
            ce.status,
            ce.scop,
            ce.data_acordarii,
            ce.ip,
            ce.locatie,
            d.nume_fisier,
            d.cale_fisier AS document_url
        FROM consimtamant_extins ce
        JOIN documente d ON ce.document_id = d.id
        WHERE ce.email = %s
        ORDER BY ce.document_id, ce.data_acordarii DESC
    """, (email,))

    consimtaminte = cursor.fetchall()

    return render_template('consimtamant.html', email=email, consimtaminte=consimtaminte)




@app.route('/admin_consimtamant')
def admin_consimtamant():
    if 'admin_email' not in session:
        return redirect(url_for('home'))

    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("SELECT * FROM documente")
    documente = cursor.fetchall()

    for doc in documente:
        # obține numărul de angajați care au semnat pentru fiecare document
        cursor.execute("""
            SELECT COUNT(*) FROM consimtamant_extins 
            WHERE scop = %s AND status = 'acordat'
        """, (doc['scop'],))
        doc['semnate'] = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) FROM consimtamant_extins 
            WHERE scop = %s AND status = 'neacordat'
        """, (doc['scop'],))
        doc['nesemnate'] = cursor.fetchone()['count']

    return render_template('admin_consimtamant.html', documente=documente)



@app.route('/modifica_status', methods=['POST'])
def modifica_status():
    if 'email' not in session:
        return redirect(url_for('home'))

    id_consimtamant = request.form['id']
    status_nou = request.form['status']

    cursor = db.cursor()

    if status_nou == 'acordat':
        cursor.execute("""
            UPDATE consimtamant_extins
            SET status = %s, data_acordarii = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (status_nou, id_consimtamant))
    else:
        cursor.execute("""
            UPDATE consimtamant_extins
            SET status = %s, data_acordarii = NULL
            WHERE id = %s
        """, (status_nou, id_consimtamant))

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

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    if 'email' not in session and 'admin_email' not in session:
        return "Unauthorized", 401

    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


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
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

        file.save(filepath)

        cursor = db.cursor()
        scop = request.form.get('scop')

        # 1. Salvăm documentul în tabela "documente" (doar numele, nu calea completă!)
        cursor.execute(
            "INSERT INTO documente (nume_fisier, cale_fisier, scop) VALUES (%s, %s, %s) RETURNING id",
            (filename, filename, scop)
        )
        document_id = cursor.fetchone()[0]

        # 2. Selectăm toți angajații existenți
        cursor.execute("SELECT email FROM users WHERE role = 'angajat'")
        angajati = cursor.fetchall()

        # 3. Inserăm un rând în consimtamant_extins pentru fiecare angajat
        for angajat in angajati:
            email = angajat[0]
            cursor.execute("""
                INSERT INTO consimtamant_extins (
                    email, status, scop, tip_consimtamant, data_acordarii,
                    ip, user_agent, locatie, pagina_origine, rol, departament, document_id
                )
                VALUES (%s, %s, %s, %s, NULL, NULL, NULL, NULL, NULL, 'angajat', NULL, %s)
            """, (
                email, 'neacordat', scop, 'explicit', document_id
            ))

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

@app.route('/documente')
def documente():
    try:
        if 'email' not in session:
            return redirect(url_for('login'))

        cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT * FROM documente")
        documente = cursor.fetchall()

        return render_template('documente.html', documente=documente)
    
    except Exception as e:
        return f"<h2>Eroare în /documente:</h2><pre>{e}</pre>"

@app.route('/acorda_consimtamant/<int:document_id>')
def acorda_consimtamant(document_id):
    if 'email' not in session:
        return redirect(url_for('login'))

    email = session['email']
    ip = request.remote_addr
    user_agent = request.user_agent.string
    locatie = "RO"
    pagina_origine = request.referrer or request.url
    rol = 'angajat'

    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO consimtamant_extins (
            email, status, scop, tip_consimtamant, data_acordarii,
            ip, user_agent, locatie, pagina_origine, rol, departament, document_id
        )
        SELECT %s, %s, d.scop, %s, CURRENT_TIMESTAMP,
               %s, %s, %s, %s, %s, u.functie, d.id
        FROM documente d
        JOIN users u ON u.email = %s
        WHERE d.id = %s
    """, (
        email, 'acordat', 'explicit',
        ip, user_agent, locatie, pagina_origine, rol,
        email, document_id
    ))
    db.commit()

    flash('Consimțământul a fost acordat cu succes!', 'success')
    return redirect(url_for('documente'))


@app.route('/refuza_consimtamant/<int:document_id>')
def refuza_consimtamant(document_id):
    if 'email' not in session:
        return redirect(url_for('login'))

    email = session['email']
    ip = request.remote_addr
    user_agent = request.user_agent.string
    locatie = "RO"
    pagina_origine = request.referrer or request.url
    rol = 'angajat'

    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO consimtamant_extins (
            email, status, scop, tip_consimtamant, data_acordarii,
            ip, user_agent, locatie, pagina_origine, rol, departament, document_id
        )
        SELECT %s, %s, d.scop, %s, CURRENT_TIMESTAMP,
               %s, %s, %s, %s, %s, u.functie, d.id
        FROM documente d
        JOIN users u ON u.email = %s
        WHERE d.id = %s
    """, (
        email, 'neacordat', 'explicit',
        ip, user_agent, locatie, pagina_origine, rol,
        email, document_id
    ))
    db.commit()

    flash('Consimțământul a fost refuzat cu succes!', 'info')
    return redirect(url_for('documente'))

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
@app.route('/vizualizeaza_consimtamant')
def vizualizeaza_consimtamant():
    if 'email' not in session:
        return redirect(url_for('home'))

    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT * FROM documente ORDER BY id DESC LIMIT 1")
    document = cursor.fetchone()

    return render_template("vizualizeaza_consimtamant.html", document=document)

@app.route('/descarca_raport')
def descarca_raport():
    if 'admin_email' not in session:
        return redirect(url_for('admin_login'))

    cursor = db.cursor()
    cursor.execute("""
        SELECT d.nume_fisier, d.scop,
               COUNT(CASE WHEN ce.status = 'acordat' THEN 1 END) AS total_acordate,
               COUNT(CASE WHEN ce.status = 'neacordat' THEN 1 END) AS total_neacordate
        FROM documente d
        LEFT JOIN consimtamant_extins ce ON d.id = ce.document_id
        GROUP BY d.id, d.nume_fisier, d.scop
    """)
    rezultate = cursor.fetchall()

    # Creăm workbook Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Raport Consimțăminte"

    # Scriem headerul
    ws.append(["Nume fișier", "Scop", "Total acordate", "Total neacordate"])

    # Adăugăm datele
    for row in rezultate:
        ws.append(row)

    # Salvăm într-un fișier temporar
    fisier_temporar = BytesIO()
    wb.save(fisier_temporar)
    fisier_temporar.seek(0)

    return send_file(
        fisier_temporar,
        as_attachment=True,
        download_name="raport_consimtamant.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == '__main__':
    app.run(debug=True)
