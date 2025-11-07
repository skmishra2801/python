from flask import Flask, render_template, request, redirect, url_for, flash
from flask_mysqldb import MySQL
import os
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

app = Flask(__name__)
app.secret_key = 'many random bytes'
#app.config['MYSQL_HOST'] = 'localhost'
#app.config['MYSQL_USER'] = 'root'
#app.config['MYSQL_PASSWORD'] = 'root'
#app.config['MYSQL_DB'] = 'cpl'

#aiven
load_dotenv()
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.config['MYSQL_PORT'] = 10985
mysql = MySQL(app)

@app.route('/', methods=['GET'])
@app.route('/<team>', methods=['GET'])
def home(team=None):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM teambalance")
    data = cur.fetchall()
    cur.close()

    team_summary = []

    for row in data:
        selected_team = row[0]  # Extract team name

        # Get opening balance for the selected team
        cur = mysql.connection.cursor()
        cur.execute("SELECT openingbalance FROM teambalance WHERE team = %s", (selected_team,))
        opening_result = cur.fetchone()
        cur.close()
        opening_balance = opening_result[0] if opening_result else 0

        # Get spent amount for the selected team
        cur = mysql.connection.cursor()
        cur.execute("SELECT SUM(Amount) FROM player_list WHERE SoldTo = %s", (selected_team,))
        spent_result = cur.fetchone()
        cur.close()
        spent = spent_result[0] if spent_result[0] is not None else 0

        # Get player count for the selected team
        cur = mysql.connection.cursor()
        cur.execute("SELECT COUNT(playername) FROM cpl.player_list WHERE soldto = %s", (selected_team,))
        playercount = cur.fetchone()
        cur.close()
        count = playercount[0] if playercount[0] is not None else 0

        remaining = opening_balance - spent

        team_summary.append({
            'team': selected_team,
            'openingbalance': opening_balance,
            'spentamount': spent,
            'balance': remaining,
            'players': count
        })

    return render_template(
        "home.html",
        team_summary=team_summary,
        selected_team=team
    )


@app.route('/playerList', methods=['GET'])
def playerList():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM player_list")
    data = cur.fetchall()
    cur.close()

    # Convert photo field to string if it's bytes
    cleaned_data = []
    for row in data:
        row = list(row)
        if isinstance(row[6], bytes):
            row[6] = row[6].decode('utf-8')
        cleaned_data.append(row)
    return render_template("playerList.html", player_list=cleaned_data)


@app.route('/addPlayer', methods=['GET'])
def addPlayer():
    return render_template('addplayer.html')


UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Now safely check and create the folder
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])


@app.route('/insert', methods=['POST'])
def insert():
    if request.method == "POST":
        #flash("Data Inserted Successfully")
        name = request.form['name']
        jerseyNumber = request.form['jerseyNumber']
        jerseySize = request.form['jerseySize']
        role = request.form['role']
        matchFee = request.form['matchFee']
        soldTo = request.form['soldTo']

        # Handle photo upload
        photo_file = request.files['photo']
        if photo_file and photo_file.filename:
            photo_filename = secure_filename(photo_file.filename)
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], photo_filename)
            photo_file.save(photo_path)
        else:
            #flash("No photo uploaded or invalid file.")
            return redirect(url_for('addPlayer'))

        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO player_list (PlayerName, jerseyNumber, jerseySize, category, payment, photo, soldTo)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (name, jerseyNumber, jerseySize, role, matchFee, photo_filename, soldTo))
        mysql.connection.commit()
        cur.close()

        return redirect(url_for('playerList'))


@app.route('/edit-player/<int:serial>', methods=['GET', 'POST'])
def edit_player(serial):
    if request.method == "POST":
        fields = []
        values = []

        # Collect only non-empty fields
        if request.form.get('PlayerName'):
            fields.append("PlayerName=%s")
            values.append(request.form['PlayerName'])

        if request.form.get('jerseyNumber'):
            fields.append("jerseyNumber=%s")
            values.append(request.form['jerseyNumber'])

        if request.form.get('jerseySize'):
            fields.append("jerseySize=%s")
            values.append(request.form['jerseySize'])

        if request.form.get('role'):
            fields.append("category=%s")
            values.append(request.form['role'])

        if request.form.get('matchFee'):
            fields.append("payment=%s")
            values.append(request.form['matchFee'])

        if request.form.get('soldTo'):
            fields.append("soldTo=%s")
            values.append(request.form['soldTo'])

        # Handle photo upload
        photo_file = request.files.get('photo')
        if photo_file and photo_file.filename:
            photo_filename = secure_filename(photo_file.filename)
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], photo_filename)
            photo_file.save(photo_path)
            fields.append("photo=%s")
            values.append(photo_filename)
        else:
            existing_photo = request.form.get('existing_photo')
            if existing_photo:
                fields.append("photo=%s")
                values.append(existing_photo)

        # Only run update if there are fields to update
        if fields:
            query = f"UPDATE player_list SET {', '.join(fields)} WHERE serial=%s"
            values.append(serial)

            cur = mysql.connection.cursor()
            cur.execute(query, tuple(values))
            mysql.connection.commit()
            cur.close()

            #flash("Player updated successfully.")
        else:
            flash("No fields to update.")

        return redirect(url_for('playerList'))

    else:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM player_list WHERE serial = %s", (serial,))
        player = cur.fetchone()
        cur.close()

        if player:
            player = list(player)
            if isinstance(player[6], bytes):
                player[6] = player[6].decode('utf-8')
            return render_template('editplayer.html', player=player)
        else:
            #flash("Player not found.")
            return redirect(url_for('playerList'))


@app.route('/delete-player/<int:serial>')
def delete_player(serial):
    #flash("Record Has Been Deleted Successfully")
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM player_list WHERE serial=%s", (serial,))
    mysql.connection.commit()
    return redirect(url_for('playerList'))


@app.route('/team-picture', methods=['GET'])
def team_picture():
    selected_team = request.args.get('team')
    photos = []

    if selected_team:
        cur = mysql.connection.cursor()
        cur.execute("SELECT photo FROM player_list WHERE soldTo = %s", (selected_team,))
        results = cur.fetchall()
        cur.close()
        photos = [row[0].decode('utf-8') if isinstance(row[0], bytes) else row[0] for row in results]


    return render_template('teampic.html', selected_team=selected_team, photos=photos)


@app.route('/update-team', methods=['GET', 'POST'])
@app.route('/update-team/<int:serial>', methods=['POST'])
def update_team(serial=None):
    selected_serial = request.form.get('serial') or request.args.get('serial')
    selected_player = None

    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT serial, PlayerName, jerseyNumber, jerseySize, category, payment, photo, soldTo, amount FROM player_list")
    players = cur.fetchall()

    if selected_serial:
        cur.execute("SELECT * FROM player_list WHERE serial = %s", (selected_serial,))
        selected_player = cur.fetchone()
        if selected_player and isinstance(selected_player[6], bytes):
            selected_player = list(selected_player)
            selected_player[6] = selected_player[6].decode('utf-8')

    if request.method == 'POST':
        team = request.form.get('team')
        amount = request.form.get('amount')
        if team and selected_serial:
            cur.execute("UPDATE player_list SET soldTo = %s, amount = %s WHERE serial = %s", (team, amount, selected_serial))
            mysql.connection.commit()
            #flash("Team updated successfully.")

    cur.close()
    return render_template('updateTeam.html', players=players, selected_serial=selected_serial,
                           selected_player=selected_player)


@app.route('/match-schedule')
def match_schedule():
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, `day`, `time`, `match`, `schedule`, `winner` FROM match_schedule ORDER BY `day`, `time`")

    results = cur.fetchall()
    cur.close()

    matches = [
        {
            'id': row[0],
            'day': row[1],
            'time': row[2],
            'match': row[3],
            'schedule': row[4],
            'winner': row[5]
        }
        for row in results
    ]

    return render_template('schedule.html', matches=matches)


@app.route('/addMatch', methods=['GET'])
def addMatch():
    return render_template('addMatch.html')


@app.route('/add-match', methods=['POST'])
def add_match():
    if request.method == 'POST':
        day = request.form['day']
        time = request.form['time']
        team1 = request.form['team1']
        team2 = request.form['team2']
        #winner = request.form['winner'] or None

        if not all([day, time, team1, team2]):
            #flash("Please fill in all required fields.")
            return redirect(url_for('match_schedule'))  # or your actual schedule route

        match = f"{team1} vs {team2}"
        schedule = f"{day} {time}"

        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO match_schedule (`day`, `time`, `match`, `schedule`)
            VALUES (%s, %s, %s, %s)
        """, (day, time, match, schedule))
        mysql.connection.commit()
        cur.close()

        #flash("Match added successfully.")
        return redirect(url_for('match_schedule'))  # make sure this route exists
    else:
        return redirect(url_for('match_schedule'))


@app.route('/update-winner', methods=['POST'])
def update_winner():
    match_id = request.form.get('match_id')
    winner = request.form.get('winner')

    try:
        match_id = int(match_id)
    except (TypeError, ValueError):
        #flash("Invalid match ID.")
        return redirect(url_for('match_schedule'))

    if not winner:
        #flash("Please select a winner.")
        return redirect(url_for('match_schedule'))

    cur = mysql.connection.cursor()
    cur.execute("UPDATE match_schedule SET winner = %s WHERE id = %s", (winner, match_id))
    mysql.connection.commit()
    cur.close()

    #flash("Winner updated successfully.")
    return redirect(url_for('match_schedule'))


@app.route('/delete-schedule/<int:id>')
def delete_schedule(id):
    #flash("Record Has Been Deleted Successfully")
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM match_schedule WHERE id=%s", (id,))
    mysql.connection.commit()
    return redirect(url_for('match_schedule'))




if __name__ == "__main__":
    app.run(debug=True)
