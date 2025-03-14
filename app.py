from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import func
from datetime import datetime, timedelta

app = Flask(__name__)

# Configuração do Banco de Dados
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///saldos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "surebet_secret_key"  # Necessário para mensagens flash
db = SQLAlchemy(app)
#app.run(host="192.168.1.105", port=5000, debug=True)

# Modelo de Casa de Aposta
class CasaAposta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    saldo = db.Column(db.Float, nullable=False)

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
    valor_total = db.Column(db.Float, nullable=True)  # Valor total apostado
    percentual_lucro = db.Column(db.Float, nullable=True)  # Percentual de lucro
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)  # Data de cadastro
    status = db.Column(db.String(20), default='Pendente')  # Status da surebet (Pendente, Finalizada, etc.)

    casa_1 = db.relationship('CasaAposta', foreign_keys=[casa_1_id])
    casa_2 = db.relationship('CasaAposta', foreign_keys=[casa_2_id])
    casa_3 = db.relationship('CasaAposta', foreign_keys=[casa_3_id])

# Função para calcular o saldo em aposta para cada casa
def calcular_saldo_em_aposta():
    casas = CasaAposta.query.all()
    surebets_pendentes = Surebet.query.filter_by(status='Pendente').all()
    
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


with app.app_context():
    db.create_all() 

@app.route('/')
def home():
    # Obter parâmetros de filtro
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    casa_nome = request.args.get('casa_nome')
    status = request.args.get('status')
    
    # Base query para surebets
    query = Surebet.query
    
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

@app.route('/cadastrar_casa', methods=['GET', 'POST'])
def cadastrar_casa():
    if request.method == 'POST':
        nome = request.form['nome']
        saldo = float(request.form['saldo'])
        
        nova_casa = CasaAposta(nome=nome, saldo=saldo)
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

@app.route('/adicionar_surebet', methods=['GET', 'POST'])
def adicionar_surebet():
    casas = CasaAposta.query.all()
    if request.method == 'POST':
        casa_1_id = request.form['casa_1']
        casa_2_id = request.form['casa_2']
        casa_3_id = request.form.get('casa_3')

        odd_1 = float(request.form['odd_1'])
        odd_2 = float(request.form['odd_2'])
        odd_3 = float(request.form['odd_3']) if request.form.get('odd_3') and request.form.get('odd_3') != '' else 0.0

        valor_1 = float(request.form['valor_1'])
        valor_2 = float(request.form['valor_2'])
        valor_3 = float(request.form['valor_3']) if request.form.get('valor_3') and request.form.get('valor_3') != '' else 0.0

        # Calcular valor total apostado
        valor_total = valor_1 + valor_2 + (valor_3 if casa_3_id and casa_3_id != '' else 0)

        # Calcular retornos por casa
        retorno_1 = valor_1 * odd_1
        retorno_2 = valor_2 * odd_2
        retorno_3 = valor_3 * odd_3 if (casa_3_id and casa_3_id != '' and valor_3 > 0 and odd_3 > 0) else float('inf')
        
        # Determinar o menor retorno (lucro garantido)
        min_retorno = min(retorno_1, retorno_2, retorno_3)
        
        # Calcular lucro estimado e percentual
        lucro_estimado = min_retorno - valor_total
        percentual_lucro = (lucro_estimado / valor_total) * 100 if valor_total > 0 else 0

        # Obter as casas de apostas
        casa_1 = CasaAposta.query.get(casa_1_id)
        casa_2 = CasaAposta.query.get(casa_2_id)
        casa_3 = CasaAposta.query.get(casa_3_id) if casa_3_id and casa_3_id != '' else None

        # Verificar se há saldo suficiente em cada casa
        if casa_1.saldo < valor_1:
            flash(f'Saldo insuficiente na casa {casa_1.nome}!', 'danger')
            return redirect(url_for('adicionar_surebet'))
        
        if casa_2.saldo < valor_2:
            flash(f'Saldo insuficiente na casa {casa_2.nome}!', 'danger')
            return redirect(url_for('adicionar_surebet'))
        
        if casa_3 and valor_3 > 0 and casa_3.saldo < valor_3:
            flash(f'Saldo insuficiente na casa {casa_3.nome}!', 'danger')
            return redirect(url_for('adicionar_surebet'))

        # Deduzir os valores das casas de apostas
        if casa_1:
            casa_1.saldo -= valor_1
        if casa_2:
            casa_2.saldo -= valor_2
        if casa_3 and valor_3 > 0:
            casa_3.saldo -= valor_3

        # Criar a nova surebet
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
            status='Pendente'
        )

        db.session.add(nova_surebet)
        db.session.commit()
        flash('Surebet cadastrada com sucesso!', 'success')
        return redirect(url_for('home'))

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