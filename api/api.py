from flask import Flask, request, jsonify
import mysql.connector
from datetime import datetime
app = Flask(__name__)

# Conectare la baza de date
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Adriana1!",  # schimbă cu parola ta
    database="gdpr_system"
)

@app.route('/api/consimtamant/extended', methods=['POST'])
def consimtamant_extins():
    data = request.get_json()

    try:
        email = data['email']
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        status = data['status']
        scop = data.get('scop')
        tip_consimtamant = data.get('tip_consimtamant', 'explicit')
        data_acordarii_raw = data.get('data_acordarii')
        data_acordarii = datetime.fromisoformat(data_acordarii_raw.replace("Z", "")).strftime('%Y-%m-%d %H:%M:%S') if data_acordarii_raw else None

        document_url = data.get('document_url')

        metadata = data.get('metadata', {})
        ip = metadata.get('ip')
        user_agent = metadata.get('user_agent')
        locatie = metadata.get('locatie')
        pagina_origine = metadata.get('pagina_origine')

        detalii_utilizator = data.get('detalii_utilizator', {})
        rol = detalii_utilizator.get('rol')
        departament = detalii_utilizator.get('departament')

        cursor = db.cursor()
        query = """
            INSERT INTO consimtamant_extins (
                email, first_name, last_name, status, scop,
                tip_consimtamant, data_acordarii, document_url,
                ip, user_agent, locatie, pagina_origine,
                rol, departament
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        values = (
            email, first_name, last_name, status, scop,
            tip_consimtamant, data_acordarii, document_url,
            ip, user_agent, locatie, pagina_origine,
            rol, departament
        )

        cursor.execute(query, values)
        db.commit()

        return jsonify({
            "mesaj": "Consimțământ extins salvat cu succes.",
            "email": email,
            "status": status
        }), 201

    except Exception as e:
        return jsonify({"eroare": str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True, port=5001)
