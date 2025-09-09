from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, FloatField, IntegerField, SelectField, FileField, PasswordField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Optional
from flask_wtf.file import FileAllowed
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import base64
from functools import wraps
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from io import BytesIO
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'votre-cle-secrete-a-changer'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///galerie.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

db = SQLAlchemy(app)

# Créer le dossier uploads s'il n'existe pas
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ===============================
# MODÈLES DE BASE DE DONNÉES
# ===============================

class Tableau(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    qte_tableaux = db.Column(db.Integer, nullable=False, default=1)
    qte_reproduits = db.Column(db.Integer, nullable=False, default=0)
    titre = db.Column(db.String(200), nullable=False)
    format_hxl = db.Column(db.String(50), nullable=False)  # "60x40"
    technique = db.Column(db.String(100), nullable=False)
    themes = db.Column(db.String(200))
    prix = db.Column(db.Float, nullable=False)
    lieux = db.Column(db.String(200))
    date_crea = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    date_modif = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    photo = db.Column(db.Text)  # Base64 de l'image ou chemin vers Google Drive
    
    def __repr__(self):
        return f'<Tableau {self.titre}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'qte_tableaux': self.qte_tableaux,
            'qte_reproduits': self.qte_reproduits,
            'titre': self.titre,
            'format_hxl': self.format_hxl,
            'technique': self.technique,
            'themes': self.themes,
            'prix': self.prix,
            'lieux': self.lieux,
            'date_crea': self.date_crea.strftime('%d/%m/%Y'),
            'date_modif': self.date_modif.strftime('%d/%m/%Y'),
            'photo': self.photo
        }

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

# ===============================
# FORMULAIRES
# ===============================

class TableauForm(FlaskForm):
    qte_tableaux = IntegerField('Quantité de tableaux', validators=[DataRequired(), NumberRange(min=1)], default=1)
    qte_reproduits = IntegerField('Quantité reproduits', validators=[DataRequired(), NumberRange(min=0)], default=0)
    titre = StringField('Titre', validators=[DataRequired()])
    largeur = IntegerField('Largeur (cm)', validators=[DataRequired(), NumberRange(min=1)])
    hauteur = IntegerField('Hauteur (cm)', validators=[DataRequired(), NumberRange(min=1)])
    technique = SelectField('Technique', validators=[DataRequired()], choices=[
        ('', 'Choisir une technique'),
        ('Huile sur toile', 'Huile sur toile'),
        ('Acrylique sur toile', 'Acrylique sur toile'),
        ('Aquarelle', 'Aquarelle'),
        ('Pastel', 'Pastel'),
        ('Gouache', 'Gouache'),
        ('Encre', 'Encre'),
        ('Technique mixte', 'Technique mixte'),
        ('Autre', 'Autre')
    ])
    themes = StringField('Thèmes')
    prix = FloatField('Prix (€)', validators=[DataRequired(), NumberRange(min=0)])
    lieux = StringField('Lieux')
    photo = FileField('Photo', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images seulement!')])
    submit = SubmitField('Sauvegarder')

class LoginForm(FlaskForm):
    username = StringField('Nom d\'utilisateur', validators=[DataRequired()])
    password = PasswordField('Mot de passe', validators=[DataRequired()])
    submit = SubmitField('Connexion')

class ContactForm(FlaskForm):
    nom = StringField('Nom', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    sujet = StringField('Sujet', validators=[DataRequired()])
    message = TextAreaField('Message', validators=[DataRequired()])
    submit = SubmitField('Envoyer')

# ===============================
# DÉCORATEURS
# ===============================

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('Accès refusé. Veuillez vous connecter.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# ===============================
# ROUTES PUBLIQUES
# ===============================

@app.route('/')
def index():
    # Carrousel des 10 derniers tableaux
    derniers_tableaux = Tableau.query.order_by(Tableau.date_crea.desc()).limit(10).all()
    return render_template('index.html', derniers_tableaux=derniers_tableaux)

@app.route('/galerie')
def galerie():
    page = request.args.get('page', 1, type=int)
    tableaux = Tableau.query.order_by(Tableau.date_crea.desc()).paginate(
        page=page, per_page=12, error_out=False
    )
    return render_template('galerie.html', tableaux=tableaux)

@app.route('/tableau/<int:id>')
def tableau_detail(id):
    tableau = Tableau.query.get_or_404(id)
    return render_template('tableau_detail.html', tableau=tableau)

@app.route('/contacter', methods=['GET', 'POST'])
def contacter():
    form = ContactForm()
    if form.validate_on_submit():
        # Ici vous pouvez traiter le message (envoyer email, sauvegarder, etc.)
        flash('Message envoyé avec succès!', 'success')
        return redirect(url_for('contacter'))
    return render_template('contacter.html', form=form)

# ===============================
# ROUTES ADMIN
# ===============================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    form = LoginForm()
    if form.validate_on_submit():
        admin = Admin.query.filter_by(username=form.username.data).first()
        if admin and check_password_hash(admin.password_hash, form.password.data):
            session['admin_logged_in'] = True
            session['admin_username'] = admin.username
            flash('Connexion réussie!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Nom d\'utilisateur ou mot de passe incorrect.', 'error')
    return render_template('admin/login.html', form=form)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    flash('Déconnexion réussie.', 'info')
    return redirect(url_for('index'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    total_tableaux = Tableau.query.count()
    derniers_tableaux = Tableau.query.order_by(Tableau.date_crea.desc()).limit(5).all()
    return render_template('admin/dashboard.html', 
                         total_tableaux=total_tableaux,
                         derniers_tableaux=derniers_tableaux)

@app.route('/admin/tableaux')
@admin_required
def admin_tableaux():
    page = request.args.get('page', 1, type=int)
    tableaux = Tableau.query.order_by(Tableau.date_crea.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template('admin/tableaux.html', tableaux=tableaux)

@app.route('/admin/tableau/nouveau', methods=['GET', 'POST'])
@admin_required
def admin_nouveau_tableau():
    form = TableauForm()
    if form.validate_on_submit():
        # Traitement de l'image
        photo_data = None
        if form.photo.data:
            file = form.photo.data
            if file.filename != '':
                # Convertir en base64
                photo_data = base64.b64encode(file.read()).decode('utf-8')
                file.seek(0)  # Reset pour éventuels autres traitements
        
        tableau = Tableau(
            qte_tableaux=form.qte_tableaux.data,
            qte_reproduits=form.qte_reproduits.data,
            titre=form.titre.data,
            format_hxl=f"{form.largeur.data}x{form.hauteur.data}",
            technique=form.technique.data,
            themes=form.themes.data,
            prix=form.prix.data,
            lieux=form.lieux.data,
            photo=photo_data
        )
        
        db.session.add(tableau)
        db.session.commit()
        flash('Tableau ajouté avec succès!', 'success')
        return redirect(url_for('admin_tableaux'))
    
    return render_template('admin/tableau_form.html', form=form, action='Ajouter')

@app.route('/admin/tableau/<int:id>/modifier', methods=['GET', 'POST'])
@admin_required
def admin_modifier_tableau(id):
    tableau = Tableau.query.get_or_404(id)
    form = TableauForm(obj=tableau)
    
    # Pré-remplir les dimensions
    if tableau.format_hxl:
        dimensions = tableau.format_hxl.split('x')
        if len(dimensions) == 2:
            form.hauteur.data = int(dimensions[0])
            form.largeur.data = int(dimensions[1])
    
    if form.validate_on_submit():
        # Traitement de l'image
        if form.photo.data and form.photo.data.filename != '':
            file = form.photo.data
            photo_data = base64.b64encode(file.read()).decode('utf-8')
            tableau.photo = photo_data
        
        tableau.qte_tableaux = form.qte_tableaux.data
        tableau.qte_reproduits = form.qte_reproduits.data
        tableau.titre = form.titre.data
        tableau.format_hxl = f"{form.largeur.data}x{form.hauteur.data}"
        tableau.technique = form.technique.data
        tableau.themes = form.themes.data
        tableau.prix = form.prix.data
        tableau.lieux = form.lieux.data
        
        db.session.commit()
        flash('Tableau modifié avec succès!', 'success')
        return redirect(url_for('admin_tableaux'))
    
    return render_template('admin/tableau_form.html', form=form, action='Modifier', tableau=tableau)

@app.route('/admin/tableau/<int:id>/supprimer', methods=['POST'])
@admin_required
def admin_supprimer_tableau(id):
    tableau = Tableau.query.get_or_404(id)
    db.session.delete(tableau)
    db.session.commit()
    flash('Tableau supprimé avec succès!', 'success')
    return redirect(url_for('admin_tableaux'))

@app.route('/admin/tableau/<int:id>/imprimer')
@admin_required
def admin_imprimer_tableau(id):
    tableau = Tableau.query.get_or_404(id)
    
    # Créer un PDF
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Titre
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, height - 100, f"Fiche d'œuvre: {tableau.titre}")
    
    y = height - 150
    p.setFont("Helvetica", 12)
    
    # Informations du tableau
    infos = [
        f"Titre: {tableau.titre}",
        f"Format: {tableau.format_hxl} cm",
        f"Technique: {tableau.technique}",
        f"Thèmes: {tableau.themes or 'Non spécifié'}",
        f"Prix: {tableau.prix}€",
        f"Lieux: {tableau.lieux or 'Non spécifié'}",
        f"Quantité: {tableau.qte_tableaux}",
        f"Quantité reproduits: {tableau.qte_reproduits}",
        f"Date de création: {tableau.date_crea.strftime('%d/%m/%Y')}",
        f"Dernière modification: {tableau.date_modif.strftime('%d/%m/%Y')}"
    ]
    
    for info in infos:
        p.drawString(100, y, info)
        y -= 25
    
    p.save()
    buffer.seek(0)
    
    return send_file(
        BytesIO(buffer.read()),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'tableau_{tableau.id}_{tableau.titre}.pdf'
    )

@app.route('/admin/export/liste')
@admin_required
def admin_export_liste():
    tableaux = Tableau.query.all()
    
    # Créer un PDF avec la liste
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, height - 50, "Liste des œuvres")
    
    y = height - 100
    p.setFont("Helvetica", 10)
    
    # Headers
    p.drawString(50, y, "ID")
    p.drawString(80, y, "Titre")
    p.drawString(250, y, "Format")
    p.drawString(320, y, "Technique")
    p.drawString(450, y, "Prix")
    y -= 20
    
    for tableau in tableaux:
        if y < 50:  # Nouvelle page si nécessaire
            p.showPage()
            y = height - 50
