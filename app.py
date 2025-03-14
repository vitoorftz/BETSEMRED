from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from sqlalchemy import or_

# Configuração do app
app = Flask(__name__)

# Configurações para ambiente de produção no AWS App Runner
if os.environ.get('FLASK_ENV') == 'production':
    # Usar MySQL em produção (AWS RDS ou outro banco de dados)
    db_user = os.environ.get('DB_USER', 'default_user')
    db_password = os.environ.get('DB_PASSWORD', 'default_password')
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_name = os.environ.get('DB_NAME', 'surebet')
    
    app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_name}'
    app.debug = False
else:
    # Usar SQLite em desenvolvimento local
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///saldos.db'
    app.debug = True

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'surebet_secret_key')  # Melhor usar variável de ambiente
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # Verifica conexões antes de usá-las
    'pool_recycle': 3600,   # Recicla conexões a cada hora
    'pool_size': 10,        # Limita o tamanho do pool de conexões
    'max_overflow': 20      # Permite até 20 conexões extras em picos
}

# Inicialização do banco de dados
db = SQLAlchemy(app)

# Configuração do Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Faça login para acessar esta página.'
login_manager.login_message_category = 'info'

# Definição dos modelos de dados
class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuario'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)  # Adiciona índice
    password_hash = db.Column(db.String(200), nullable=False)
    casas = db.relationship('CasaAposta', backref='usuario', lazy='dynamic')  # Lazy loading para otimizar
    surebets = db.relationship('Surebet', backref='usuario', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class CasaAposta(db.Model):
    __tablename__ = 'casa_aposta'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    saldo = db.Column(db.Float, nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False, index=True)  # Adiciona índice

class Surebet(db.Model):
    __tablename__ = 'surebet'
    id = db.Column(db.Integer, primary_key=True)
    casa_1_id = db.Column(db.Integer, db.ForeignKey('casa_aposta.id'), nullable=False, index=True)  # Adiciona índice
    casa_2_id = db.Column(db.Integer, db.ForeignKey('casa_aposta.id'), nullable=False, index=True)
    casa_3_id = db.Column(db.Integer, db.ForeignKey('casa_aposta.id'), nullable=True, index=True)
    odd_1 = db.Column(db.Float, nullable=False)
    odd_2 = db.Column(db.Float, nullable=False)
    odd_3 = db.Column(db.Float, nullable=True)
    valor_1 = db.Column(db.Float, nullable=False)
    valor_2 = db.Column(db.Float, nullable=False)
    valor_3 = db.Column(db.Float, nullable=True)
    lucro_estimado = db.Column(db.Float, nullable=True)
    valor_total = db.Column(db.Float, nullable=True)
    percentual_lucro = db.Column(db.Float, nullable=True)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow, index=True)  # Adiciona índice para buscas por data
    status = db.Column(db.String(20), default='Pendente', index=True)  # Adiciona índice para filtragem
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False, index=True)

    # Define lazy loading para melhorar performance
    casa_1 = db.relationship('CasaAposta', foreign_keys=[casa_1_id], lazy='joined')
    casa_2 = db.relationship('CasaAposta', foreign_keys=[casa_2_id], lazy='joined')
    casa_3 = db.relationship('CasaAposta', foreign_keys=[casa_3_id], lazy='joined')

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# Função otimizada para calcular saldo em aposta usando agregação de banco de dados
def calcular_saldo_em_aposta():
    # Busca todas as casas do usuário em uma única query
    casas = CasaAposta.query.filter_by(usuario_id=current_user.id).all()
    casas_dict = {casa.id: casa for casa in casas}
    
    # Inicializa saldo em aposta para todas as casas
    for casa in casas:
        casa.saldo_em_aposta = 0.0
    
    # Busca somatórios por casa usando agregação do SQL ao invés de loop Python
    surebet_values = db.session.query(
        Surebet.casa_1_id, 
        db.func.sum(Surebet.valor_1).label('total_valor_1')
    ).filter_by(
        usuario_id=current_user.id, 
        status='Pendente'
    ).group_by(Surebet.casa_1_id).all()
    
    for casa_id, total in surebet_values:
        if casa_id in casas_dict:
            casas_dict[casa_id].saldo_em_aposta += total or 0
    
    # Repita para casa_2
    surebet_values = db.session.query(
        Surebet.casa_2_id, 
        db.func.sum(Surebet.valor_2).label('total_valor_2')
    ).filter_by(
        usuario_id=current_user.id, 
        status='Pendente'
    ).group_by(Surebet.casa_2_id).all()
    
    for casa_id, total in surebet_values:
        if casa_id in casas_dict:
            casas_dict[casa_id].saldo_em_aposta += total or 0
    
    # Repita para casa_3 (apenas para valores não nulos)
    surebet_values = db.session.query(
        Surebet.casa_3_id, 
        db.func.sum(Surebet.valor_3).label('total_valor_3')
    ).filter_by(
        usuario_id=current_user.id, 
        status='Pendente'
    ).filter(Surebet.casa_3_id != None).group_by(Surebet.casa_3_id).all()
    
    for casa_id, total in surebet_values:
        if casa_id in casas_dict:
            casas_dict[casa_id].saldo_em_aposta += total or 0
    
    # Calcular totais
    saldo_total = sum(casa.saldo for casa in casas)
    saldo_em_aposta_total = sum(getattr(casa, 'saldo_em_aposta', 0) for casa in casas)
    
    return casas, saldo_total, saldo_em_aposta_total

with app.app_context():
    db.create_all() 

# Rotas otimizadas com cache-control e melhor tratamento de erros
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        try:
            user = Usuario.query.filter_by(username=username).first()
            
            if user and user.check_password(password):
                login_user(user)
                next_page = request.args.get('next')
                flash('Login realizado com sucesso!', 'success')
                return redirect(next_page or url_for('home'))
            else:
                flash('Nome de usuário ou senha incorretos.', 'danger')
        except Exception as e:
            app.logger.error(f"Erro no login: {str(e)}")
            flash('Ocorreu um erro durante o login. Tente novamente.', 'danger')
    
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        try:
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
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Erro no registro: {str(e)}")
            flash('Ocorreu um erro durante o registro. Tente novamente.', 'danger')
    
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
    try:
        # Obter parâmetros de filtro
        data_inicio = request.args.get('data_inicio')
        data_fim = request.args.get('data_fim')
        casa_nome = request.args.get('casa_nome')
        status = request.args.get('status')
        
        # Base query para surebets (filtrar por usuário atual)
        query = Surebet.query.filter_by(usuario_id=current_user.id)
        
        # Aplicar filtros
        if data_inicio:
            try:
                date_inicio = datetime.strptime(data_inicio, '%Y-%m-%d')
                query = query.filter(Surebet.data_cadastro >= date_inicio)
            except ValueError:
                flash('Formato de data inválido para data de início.', 'warning')
        
        if data_fim:
            try:
                date_fim = datetime.strptime(data_fim, '%Y-%m-%d')
                # Adiciona 1 dia para incluir todo o dia final
                date_fim = date_fim + timedelta(days=1)
                query = query.filter(Surebet.data_cadastro < date_fim)
            except ValueError:
                flash('Formato de data inválido para data de fim.', 'warning')
        
        if casa_nome:
            try:
                # Filtrar surebets onde qualquer uma das casas corresponde ao ID selecionado
                casa_id = int(casa_nome)
                query = query.filter(or_(
                    Surebet.casa_1_id == casa_id,
                    Surebet.casa_2_id == casa_id,
                    Surebet.casa_3_id == casa_id
                ))
            except ValueError:
                flash('ID de casa de aposta inválido.', 'warning')
        
        if status:
            query = query.filter(Surebet.status == status)
        
        # Ordenar por data de cadastro (mais recente primeiro)
        # Usar join com eager loading para reduzir o número de consultas
        surebets = query.order_by(Surebet.data_cadastro.desc()).all()
        
        # Restante do código permanece igual
        casas, saldo_total, saldo_em_aposta_total = calcular_saldo_em_aposta()
        
        return render_template('home.html', 
                            casas=casas, 
                            surebets=surebets, 
                            saldo_total=saldo_total,
                            saldo_em_aposta_total=saldo_em_aposta_total)
    except Exception as e:
        app.logger.error(f"Erro na página inicial: {str(e)}")
        flash('Ocorreu um erro ao carregar os dados. Tente novamente.', 'danger')
        return render_template('home.html', casas=[], surebets=[], saldo_total=0, saldo_em_aposta_total=0)

@app.route('/cadastrar_casa', methods=['GET', 'POST'])
@login_required
def cadastrar_casa():
    if request.method == 'POST':
        try:
            nome = request.form.get('nome', '')
            saldo_str = request.form.get('saldo', '0')
            
            # Validação de entrada
            if not nome:
                flash('O nome da casa de aposta é obrigatório.', 'danger')
                return render_template('cadastrar_casa.html')
                
            try:
                saldo = float(saldo_str)
            except ValueError:
                flash('O saldo deve ser um número válido.', 'danger')
                return render_template('cadastrar_casa.html')
            
            nova_casa = CasaAposta(nome=nome, saldo=saldo, usuario_id=current_user.id)
            db.session.add(nova_casa)
            db.session.commit()
            
            flash('Casa de aposta cadastrada com sucesso!', 'success')
            return redirect(url_for('home'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Erro ao cadastrar casa: {str(e)}")
            flash('Ocorreu um erro ao cadastrar a casa de aposta. Tente novamente.', 'danger')
    
    return render_template('cadastrar_casa.html')

@app.route('/editar_casa/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_casa(id):
    try:
        casa = CasaAposta.query.filter_by(id=id, usuario_id=current_user.id).first_or_404()
        
        if request.method == 'POST':
            nome = request.form.get('nome', '')
            saldo_str = request.form.get('saldo', '0')
            
            # Validação de entrada
            if not nome:
                flash('O nome da casa de aposta é obrigatório.', 'danger')
                return render_template('editar_casa.html', casa=casa)
                
            try:
                saldo = float(saldo_str)
            except ValueError:
                flash('O saldo deve ser um número válido.', 'danger')
                return render_template('editar_casa.html', casa=casa)
            
            casa.nome = nome
            casa.saldo = saldo
            
            db.session.commit()
            flash('Casa de aposta atualizada com sucesso!', 'success')
            return redirect(url_for('home'))
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Erro ao editar casa: {str(e)}")
        flash('Ocorreu um erro ao editar a casa de aposta. Tente novamente.', 'danger')
        return redirect(url_for('home'))
    
    return render_template('editar_casa.html', casa=casa)

@app.route('/excluir_casa/<int:id>')
@login_required
def excluir_casa(id):
    try:
        casa = CasaAposta.query.filter_by(id=id, usuario_id=current_user.id).first_or_404()
        
        # Verificar se há surebets associadas usando uma única query
        has_surebets = db.session.query(Surebet).filter(
            or_(
                Surebet.casa_1_id == id,
                Surebet.casa_2_id == id,
                Surebet.casa_3_id == id
            )
        ).first() is not None
        
        if has_surebets:
            flash('Não é possível excluir esta casa de aposta pois ela possui surebets associadas.', 'danger')
            return redirect(url_for('home'))
        
        db.session.delete(casa)
        db.session.commit()
        
        flash('Casa de aposta excluída com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Erro ao excluir casa: {str(e)}")
        flash('Ocorreu um erro ao excluir a casa de aposta. Tente novamente.', 'danger')
    
    return redirect(url_for('home'))

@app.route('/adicionar_surebet', methods=['GET', 'POST'])
@login_required
def adicionar_surebet():
    casas = CasaAposta.query.filter_by(usuario_id=current_user.id).all()
    
    if request.method == 'POST':
        try:
            # Extrair e validar os dados do formulário
            casa_1_id = int(request.form.get('casa_1_id', 0))
            casa_2_id = int(request.form.get('casa_2_id', 0))
            casa_3_id = request.form.get('casa_3_id')
            
            odd_1 = float(request.form.get('odd_1', 0))
            odd_2 = float(request.form.get('odd_2', 0))
            odd_3 = request.form.get('odd_3')
            
            valor_1 = float(request.form.get('valor_1', 0))
            valor_2 = float(request.form.get('valor_2', 0))
            valor_3 = request.form.get('valor_3')
            
            # Converter para None quando aplicável
            casa_3_id = int(casa_3_id) if casa_3_id and casa_3_id.strip() else None
            odd_3 = float(odd_3) if odd_3 and odd_3.strip() else None
            valor_3 = float(valor_3) if valor_3 and valor_3.strip() else None
            
            # Verificar se as casas existem e pertencem ao usuário
            casa_1 = CasaAposta.query.filter_by(id=casa_1_id, usuario_id=current_user.id).first()
            casa_2 = CasaAposta.query.filter_by(id=casa_2_id, usuario_id=current_user.id).first()
            casa_3 = None
            if casa_3_id:
                casa_3 = CasaAposta.query.filter_by(id=casa_3_id, usuario_id=current_user.id).first()
            
            if not casa_1 or not casa_2 or (casa_3_id and not casa_3):
                flash('Uma ou mais casas de aposta selecionadas não foram encontradas.', 'danger')
                return render_template('adicionar_surebet.html', casas=casas)
            
            # Verifica se tem saldo suficiente
            if casa_1.saldo < valor_1 or casa_2.saldo < valor_2 or (casa_3 and valor_3 and casa_3.saldo < valor_3):
                flash('Uma ou mais casas não possuem saldo suficiente para esta aposta.', 'danger')
                return render_template('adicionar_surebet.html', casas=casas)
            
            # Calcular lucro estimado
            valor_total = valor_1 + valor_2 + (valor_3 or 0)
            
            # Cálculo para 2 casas
            if not casa_3_id:
                ganho_casa_1 = valor_1 * odd_1
                ganho_casa_2 = valor_2 * odd_2
                lucro_estimado = min(ganho_casa_1, ganho_casa_2) - valor_total
            # Cálculo para 3 casas
            else:
                ganho_casa_1 = valor_1 * odd_1
                ganho_casa_2 = valor_2 * odd_2
                ganho_casa_3 = valor_3 * odd_3
                lucro_estimado = min(ganho_casa_1, ganho_casa_2, ganho_casa_3) - valor_total
            
            percentual_lucro = (lucro_estimado / valor_total) * 100
            
            # Descontar valores dos saldos das casas
            casa_1.saldo -= valor_1
            casa_2.saldo -= valor_2
            if casa_3 and valor_3:
                casa_3.saldo -= valor_3
            
            # Criar nova surebet
            nova_surebet = Surebet(
                casa_1_id=casa_1_id,
                casa_2_id=casa_2_id,
                casa_3_id=casa_3_id,
                odd_1=odd_1,
                odd_2=odd_2,
                odd_3=odd_3,
                valor_1=valor_1,
                valor_2=valor_2,
                valor_3=valor_3,
                lucro_estimado=lucro_estimado,
                valor_total=valor_total,
                percentual_lucro=percentual_lucro,
                data_cadastro=datetime.utcnow(),
                status='Pendente',
                usuario_id=current_user.id
            )
            
            db.session.add(nova_surebet)
            db.session.commit()
            
            flash('Surebet adicionada com sucesso!', 'success')
            return redirect(url_for('home'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Erro ao adicionar surebet: {str(e)}")
            flash('Ocorreu um erro ao adicionar a surebet. Verifique os dados e tente novamente.', 'danger')
    
    return render_template('adicionar_surebet.html', casas=casas)

@app.route('/definir_resultado/<int:id>', methods=['GET', 'POST'])
@login_required
def definir_resultado(id):
    try:
        surebet = Surebet.query.filter_by(id=id, usuario_id=current_user.id).first_or_404()
        
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
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Erro ao definir resultado: {str(e)}")
        flash('Ocorreu um erro ao definir o resultado da surebet. Tente novamente.', 'danger')
        return redirect(url_for('home'))
    
    return render_template('definir_resultado.html', surebet=surebet)

@app.route('/excluir_surebet/<int:id>')
@login_required
def excluir_surebet(id):
    try:
        surebet = Surebet.query.filter_by(id=id, usuario_id=current_user.id).first_or_404()
        
        # Restaurar os saldos das casas de apostas
        if surebet.status == 'Pendente':
            # Se ainda estiver pendente, apenas devolva os valores apostados
            surebet.casa_1.saldo += surebet.valor_1
            surebet.casa_2.saldo += surebet.valor_2
            if surebet.casa_3 and surebet.valor_3:
                surebet.casa_3.saldo += surebet.valor_3
        
        # Exclua a surebet
        db.session.delete(surebet)
        db.session.commit()
        
        flash('Surebet excluída com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Erro ao excluir surebet: {str(e)}")
        flash('Ocorreu um erro ao excluir a surebet. Tente novamente.', 'danger')
    
    return redirect(url_for('home'))

@app.route('/reverter_status/<int:id>')
@login_required
def reverter_status(id):
    try:
        surebet = Surebet.query.filter_by(id=id, usuario_id=current_user.id).first_or_404()
        
        if surebet.status == 'Finalizada':
            # Reverter os ganhos da casa vencedora
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
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Erro ao reverter status: {str(e)}")
        flash('Ocorreu um erro ao reverter o status da surebet. Tente novamente.', 'danger')
    
    return redirect(url_for('home'))

# Handlers de erro para produção
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

# Criação das tabelas no primeiro acesso
with app.app_context():
    db.create_all()

# Configuração para produção
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    if os.environ.get('FLASK_ENV') == 'production':
        # Para AWS App Runner, usamos gunicorn (instalado via requirements.txt)
        # O comando será executado pelo Dockerfile ou apprunner.yaml
        import logging
        gunicorn_logger = logging.getLogger('gunicorn.error')
        app.logger.handlers = gunicorn_logger.handlers
        app.logger.setLevel(gunicorn_logger.level)
        app.run(host='0.0.0.0', port=port, debug=False)
    else:
        # Ambiente de desenvolvimento
        app.run(debug=True)