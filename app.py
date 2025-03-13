from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import func
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Primeiro, crie a aplicação Flask
app = Flask(__name__)

# Configuração do Banco de Dados
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///saldos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "surebet_secret_key"  # Necessário para mensagens flash

# Inicialize o SQLAlchemy
db = SQLAlchemy(app)

# Agora, configure o LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
#app.run(host="192.168.1.105", port=5000, debug=True)

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    casas = db.relationship('CasaAposta', backref='usuario', lazy=True)
    surebets = db.relationship('Surebet', backref='usuario', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @login_manager.user_loader
    def load_user(user_id):
        return Usuario.query.get(int(user_id))

# Modificação no modelo CasaAposta para associar a um usuário
class CasaAposta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    saldo = db.Column(db.Float, nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

# Modificação no modelo Surebet para associar a um usuário
class Surebet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    casa_1_id = db.Column(db.Integer, db.ForeignKey('casa_aposta.id'), nullable=False)
    casa_2_id = db.Column(db.Integer, db.ForeignKey('casa_aposta.id'), nullable=False)
    casa_3_id = db.Column(db.Integer, db.ForeignKey('casa_aposta.id'), nullable=True)
    odd_1 = db.Column(db.Float, nullable=False)
    odd_2 = db.Column(db.Float, nullable=False)
    odd_3 = db.Column(db.Float, nullable=True)
    valor_1 = db.Column(db.Float, nullable=False)
    valor_2 = db.Column(db.Float, nullable=False)
    valor_3 = db.Column(db.Float, nullable=True)
    lucro_estimado = db.Column(db.Float, nullable=True)
    valor_total = db.Column(db.Float, nullable=True)
    percentual_lucro = db.Column(db.Float, nullable=True)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Pendente')
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

    casa_1 = db.relationship('CasaAposta', foreign_keys=[casa_1_id])
    casa_2 = db.relationship('CasaAposta', foreign_keys=[casa_2_id])
    casa_3 = db.relationship('CasaAposta', foreign_keys=[casa_3_id])

# Modificação na função calcular_saldo_em_aposta
def calcular_saldo_em_aposta():
    casas = CasaAposta.query.filter_by(usuario_id=current_user.id).all()
    surebets_pendentes = Surebet.query.filter_by(usuario_id=current_user.id, status='Pendente').all()
    
    # Inicializar saldo em aposta como zero para todas as casas
    for casa in casas:
        casa.saldo_em_aposta = 0
    
    # Calcular saldo em aposta com base nas surebets pendentes
    for surebet in surebets_pendentes:
        # Adicionar valores apostados ao saldo em aposta de cada casa
        surebet.casa_1.saldo_em_aposta = getattr(surebet.casa_1, 'saldo_em_aposta', 0) + surebet.valor_1
        surebet.casa_2.saldo_em_aposta = getattr(surebet.casa_2, 'saldo_em_aposta', 0) + surebet.valor_2
        if surebet.casa_3 and surebet.valor_3:
            surebet.casa_3.saldo_em_aposta = getattr(surebet.casa_3, 'saldo_em_aposta', 0) + surebet.valor_3
    
    # Calcular totais
    saldo_total = sum(casa.saldo for casa in casas)
    saldo_em_aposta_total = sum(getattr(casa, 'saldo_em_aposta', 0) for casa in casas)
    
    return casas, saldo_total, saldo_em_aposta_total

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = Usuario.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Nome de usuário ou senha incorretos.', 'danger')
    
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        # Verificar se o nome de usuário já existe
        user_exists = Usuario.query.filter_by(username=username).first()
        if user_exists:
            flash('Nome de usuário já está em uso.', 'danger')
            return render_template('registro.html')
        
        # Verificar se as senhas coincidem
        if password != confirm_password:
            flash('As senhas não coincidem.', 'danger')
            return render_template('registro.html')
        
        # Criar novo usuário
        new_user = Usuario(username=username)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Conta criada com sucesso! Faça o login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('registro.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado.', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    # Obter parâmetros de filtro
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    casa_nome = request.args.get('casa_nome')
    status = request.args.get('status')
    
    # Base query para surebets (filtrar por usuário atual)
    query = Surebet.query.filter_by(usuario_id=current_user.id)
    
    # Aplicar filtros
    if data_inicio:
        date_inicio = datetime.strptime(data_inicio, '%Y-%m-%d')
        query = query.filter(Surebet.data_cadastro >= date_inicio)
    
    if data_fim:
        date_fim = datetime.strptime(data_fim, '%Y-%m-%d')
        # Adiciona 1 dia para incluir todo o dia final
        date_fim = date_fim + timedelta(days=1)
        query = query.filter(Surebet.data_cadastro < date_fim)
    
    if casa_nome:
        # Filtrar surebets onde qualquer uma das casas corresponde ao ID selecionado
        casa_id = int(casa_nome)
        query = query.filter((Surebet.casa_1_id == casa_id) | 
                             (Surebet.casa_2_id == casa_id) | 
                             (Surebet.casa_3_id == casa_id))
    
    if status:
        query = query.filter(Surebet.status == status)
    
    # Ordenar por data de cadastro (mais recente primeiro)
    surebets = query.order_by(Surebet.data_cadastro.desc()).all()
    
    # Restante do código permanece igual
    casas, saldo_total, saldo_em_aposta_total = calcular_saldo_em_aposta()
    
    return render_template('home.html', 
                          casas=casas, 
                          surebets=surebets, 
                          saldo_total=saldo_total,
                          saldo_em_aposta_total=saldo_em_aposta_total)


# Modificação na rota cadastrar_casa
@app.route('/cadastrar_casa', methods=['GET', 'POST'])
@login_required
def cadastrar_casa():
    if request.method == 'POST':
        nome = request.form['nome']
        saldo = float(request.form['saldo'])
        
        nova_casa = CasaAposta(nome=nome, saldo=saldo, usuario_id=current_user.id)
        db.session.add(nova_casa)
        db.session.commit()
        
        flash('Casa de aposta cadastrada com sucesso!', 'success')
        return redirect(url_for('home'))
    
    return render_template('cadastrar_casa.html')

@app.route('/editar_casa/<int:id>', methods=['GET', 'POST'])
def editar_casa(id):
    casa = CasaAposta.query.get_or_404(id)
    
    if request.method == 'POST':
        casa.nome = request.form['nome']
        casa.saldo = float(request.form['saldo'])
        
        db.session.commit()
        flash('Casa de aposta atualizada com sucesso!', 'success')
        return redirect(url_for('home'))
    
    return render_template('editar_casa.html', casa=casa)

@app.route('/excluir_casa/<int:id>')
def excluir_casa(id):
    casa = CasaAposta.query.get_or_404(id)
    
    # Verificar se há surebets associadas
    surebets_casa1 = Surebet.query.filter_by(casa_1_id=id).first()
    surebets_casa2 = Surebet.query.filter_by(casa_2_id=id).first()
    surebets_casa3 = Surebet.query.filter_by(casa_3_id=id).first()
    
    if surebets_casa1 or surebets_casa2 or surebets_casa3:
        flash('Não é possível excluir esta casa de aposta pois ela possui surebets associadas.', 'danger')
        return redirect(url_for('home'))
    
    db.session.delete(casa)
    db.session.commit()
    
    flash('Casa de aposta excluída com sucesso!', 'success')
    return redirect(url_for('home'))

# Modificação na rota adicionar_surebet
@app.route('/adicionar_surebet', methods=['GET', 'POST'])
@login_required
def adicionar_surebet():
    casas = CasaAposta.query.filter_by(usuario_id=current_user.id).all()
    
    if request.method == 'POST':
        # Resto do código permanece igual
        # ...
        
        # Adicionar o usuário_id à nova surebet
        nova_surebet = Surebet(
            casa_1_id=casa_1_id,
            casa_2_id=casa_2_id,
            casa_3_id=casa_3_id if casa_3_id and casa_3_id != '' else None,
            odd_1=odd_1,
            odd_2=odd_2,
            odd_3=odd_3 if casa_3_id and casa_3_id != '' else None,
            valor_1=valor_1,
            valor_2=valor_2,
            valor_3=valor_3 if casa_3_id and casa_3_id != '' else None,
            lucro_estimado=lucro_estimado,
            valor_total=valor_total,
            percentual_lucro=percentual_lucro,
            data_cadastro=datetime.utcnow(),
            status='Pendente',
            usuario_id=current_user.id
        )
        
        # Resto do código permanece igual
        # ...
    
    return render_template('adicionar_surebet.html', casas=casas)

@app.route('/definir_resultado/<int:id>', methods=['GET', 'POST'])
def definir_resultado(id):
    surebet = Surebet.query.get_or_404(id)
    
    if request.method == 'POST':
        # Obtenha qual casa ganhou da requisição
        casa_vencedora = request.form.get('casa_vencedora')
        
        # Atualize os saldos das casas de apostas
        if casa_vencedora == 'casa_1':
            # Casa 1 ganhou, recebe o valor da aposta * odd
            ganho = surebet.valor_1 * surebet.odd_1
            surebet.casa_1.saldo += ganho
            # As outras casas já tiveram seu saldo subtraído quando a aposta foi registrada
        elif casa_vencedora == 'casa_2':
            # Casa 2 ganhou, recebe o valor da aposta * odd
            ganho = surebet.valor_2 * surebet.odd_2
            surebet.casa_2.saldo += ganho
        elif casa_vencedora == 'casa_3' and surebet.casa_3:
            # Casa 3 ganhou, recebe o valor da aposta * odd
            ganho = surebet.valor_3 * surebet.odd_3
            surebet.casa_3.saldo += ganho
        
        # Atualize o status da surebet
        surebet.status = 'Finalizada'
        
        db.session.commit()
        flash('Resultado da surebet definido com sucesso!', 'success')
        return redirect(url_for('home'))
    
    return render_template('definir_resultado.html', surebet=surebet)

@app.route('/excluir_surebet/<int:id>')
def excluir_surebet(id):
    surebet = Surebet.query.get_or_404(id)
    
    # Restaurar os saldos das casas de apostas
    if surebet.status == 'Pendente':
        # Se ainda estiver pendente, apenas devolva os valores apostados
        surebet.casa_1.saldo += surebet.valor_1
        surebet.casa_2.saldo += surebet.valor_2
        if surebet.casa_3:
            surebet.casa_3.saldo += surebet.valor_3
    
    # Exclua a surebet
    db.session.delete(surebet)
    db.session.commit()
    
    flash('Surebet excluída com sucesso!', 'success')
    return redirect(url_for('home'))

@app.route('/reverter_status/<int:id>')
def reverter_status(id):
    surebet = Surebet.query.get_or_404(id)
    
    if surebet.status == 'Finalizada':
        # Reverter os ganhos da casa vencedora
        # Precisamos determinar qual casa ganhou com base nas alterações nos saldos
        
        # Primeiro, verificamos as odds e valores para identificar o possível retorno de cada casa
        retorno_casa1 = surebet.valor_1 * surebet.odd_1
        retorno_casa2 = surebet.valor_2 * surebet.odd_2
        retorno_casa3 = surebet.valor_3 * surebet.odd_3 if (surebet.casa_3 and surebet.valor_3 and surebet.odd_3) else 0
        
        # Agora, reduzimos o saldo da casa que recebeu o retorno
        if retorno_casa1 > max(retorno_casa2, retorno_casa3):
            # Casa 1 provavelmente ganhou
            surebet.casa_1.saldo -= retorno_casa1
        elif retorno_casa2 > max(retorno_casa1, retorno_casa3):
            # Casa 2 provavelmente ganhou
            surebet.casa_2.saldo -= retorno_casa2
        elif retorno_casa3 > 0:
            # Casa 3 provavelmente ganhou
            surebet.casa_3.saldo -= retorno_casa3
        
        # Volta o status para pendente
        surebet.status = 'Pendente'
        
        db.session.commit()
        flash('Status da surebet revertido para Pendente com sucesso!', 'success')
    else:
        flash('Esta surebet já está pendente!', 'warning')
    
    return redirect(url_for('home'))



if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)