import machine
from machine import Pin, ADC, PWM
import time
import dht
import network
from umqtt.simple import MQTTClient
import json

# --- PINOS DOS SENTIDOS DA CASA ---
sensor_clima = dht.DHT22(Pin(18))
sensor_gas = ADC(Pin(34))
sensor_gas.atten(ADC.ATTN_11DB) 
sensor_presenca = Pin(27, Pin.IN) 
sensor_luz = ADC(Pin(35))
sensor_luz.atten(ADC.ATTN_11DB)

# --- PINOS DOS MÚSCULOS DA CASA ---
buzzer = PWM(Pin(5))
rele_luz = Pin(23, Pin.OUT)
rele_cortina = Pin(22, Pin.OUT)
rele_ar = Pin(21, Pin.OUT)
rele_janela = Pin(17, Pin.OUT)


# --- CONFIGURAÇÕES DA CASA ---
alarme_ligado = False
modo_ar_auto = True         
ar_desligado_manual = False  
temperatura_alvo = 22       
estado_janela_manual = 0    

SERVIDOR_MENSAGENS = "broker.hivemq.com"
NOME_DA_PLACA = "casa_inteligente_gabriel"
CANAL_ENVIAR_DADOS = "gabriel/casa/sensores"
CANAL_RECEBER_COMANDOS = "gabriel/casa/comandos"

ultimo_aviso_enviado = 0
INTERVALO_AVISOS = 3000 

def conecta_wifi():
    print("Ligando antena Wi-Fi...")
    wifi = network.WLAN(network.STA_IF)
    wifi.active(True)
    if wifi.isconnected(): return
    wifi.connect("Wokwi-GUEST", "") 
    while not wifi.isconnected():
        print(".", end="")
        time.sleep(0.5)
    print("\nWi-fi Conectado! Tudo pronto.")

# --- OUVINDO OS BOTÕES DO NODE-RED ---
def ouve_node_red(topico, message):
    global alarme_ligado, modo_ar_auto, temperatura_alvo, estado_janela_manual, ar_desligado_manual
    
    comando = message.decode('utf-8')
    
    if len(comando) > 15 and "_" not in comando:
        print("-> Ignorando sinal desconhecido:", comando)
        return

    # Comandos do Alarme
    if comando == "alarme_on":
        alarme_ligado = True
        print("[ SEGURANÇA ] -> Alarme de invasão ATIVADO!")
    elif comando == "alarme_off":
        alarme_ligado = False
        desliga_barulho()
        print("[ SEGURANÇA ] -> Alarme de invasão DESATIVADO.")

    # Comandos do Modo Cinema
    elif comando == "cinema":
        if rele_cortina.value() == 0: 
            rele_cortina.value(1) 
            rele_luz.value(0)     
            print("[ MODO CINEMA ] -> ATIVADO! (Cortina Fechada, Luz Apagada)")
        else:
            rele_cortina.value(0) 
            rele_luz.value(1)     
            print("[ MODO CINEMA ] -> DESATIVADO! (Cortina Aberta, Luz Acesa)")

    # Comandos MANUAIS
    elif comando == "luz_toggle":
        if rele_luz.value() == 0:
            rele_luz.value(1)
            print("[ LUZ ] -> LIGADA")
        else:
            rele_luz.value(0)
            print("[ LUZ ] -> DESLIGADA")
            
    elif comando == "cortina_toggle":
        if rele_cortina.value() == 0:
            rele_cortina.value(1)
            print("[ CORTINA ] -> FECHADA")
        else:
            rele_cortina.value(0)
            print("[ CORTINA ] -> ABERTA")
            
    elif comando == "janela_toggle":
        if estado_janela_manual == 0:
            estado_janela_manual = 1
            print("[ JANELA ] -> ABERTA")
        else:
            estado_janela_manual = 0
            print("[ JANELA ] -> FECHADA")

    # Comandos do Ar Condicionado
    elif comando == "ar_auto":
        modo_ar_auto = True
        ar_desligado_manual = False
        print("[ AR CONDICIONADO ] -> Voltou para o modo AUTOMÁTICO.")
        
    elif comando == "ar_off":
        modo_ar_auto = False
        ar_desligado_manual = True
        print("[ AR CONDICIONADO ] -> Desligado MANUALMENTE pelo painel.")
        
    elif comando == "ar_mais":
        modo_ar_auto = False 
        ar_desligado_manual = False
        temperatura_alvo += 1
        print("[ AR CONDICIONADO ] -> Alvo subiu para {}°C".format(temperatura_alvo))
        
    elif comando == "ar_menos":
        modo_ar_auto = False
        ar_desligado_manual = False
        temperatura_alvo -= 1
        print("[ AR CONDICIONADO ] -> Alvo desceu para {}°C".format(temperatura_alvo))

def prepara_mensageiro():
    carteiro = MQTTClient(NOME_DA_PLACA, SERVIDOR_MENSAGENS)
    carteiro.set_callback(ouve_node_red)
    carteiro.connect()
    carteiro.subscribe(CANAL_RECEBER_COMANDOS)
    return carteiro

def toca_sirene():
    buzzer.freq(1000)
    buzzer.duty(512)

def desliga_barulho():
    buzzer.duty(0)

# Deixando tudo desligado antes de começar
desliga_barulho()
rele_luz.value(0); rele_cortina.value(0)
rele_ar.value(0); rele_janela.value(0)

conecta_wifi()
mensageiro = prepara_mensageiro() 

print("=======================================")
print(" CASA INTELIGENTE RODANDO ")
print("=======================================")

while True:
    try:
        agora = time.ticks_ms()
        mensageiro.check_msg()

        sensor_clima.measure()
        temperatura = sensor_clima.temperature()
        nivel_gas = sensor_gas.read()
        movimento = sensor_presenca.value()

        # --- PROTEÇÃO MÁXIMA ---
        if temperatura > 45 or nivel_gas > 2000:
            toca_sirene()
            rele_janela.value(1) 
            rele_ar.value(0)     
        else:
            desliga_barulho()
            rele_janela.value(estado_janela_manual)
            
            # --- LÓGICA DO AR CONDICIONADO ---
            if modo_ar_auto:
                if temperatura > 28:
                    rele_ar.value(1)
                elif temperatura < 17:
                    rele_ar.value(1) 
                elif 20 <= temperatura <= 24: 
                    rele_ar.value(0)
            elif ar_desligado_manual:
                # Se você apertou para desligar, o motor morre aqui e ignora o resto
                rele_ar.value(0)
            else:
                # Controle por temperatura alvo manual
                if temperatura >= (temperatura_alvo + 1) or temperatura <= (temperatura_alvo - 1):
                    rele_ar.value(1) 
                else:
                    rele_ar.value(0)

            # --- LÓGICA DE INVASÃO ---
            if alarme_ligado and movimento == 1:
                toca_sirene()

        # --- RESUMO NA TELA E ENVIO PARA O NODE-RED ---
        if time.ticks_diff(agora, ultimo_aviso_enviado) >= INTERVALO_AVISOS:
            
            # Ajustando o texto do modo para mostrar no resumo
            if modo_ar_auto:
                modo_ar = "AUTO"
            elif ar_desligado_manual:
                modo_ar = "DESLIGADO MANUAL"
            else:
                modo_ar = "MANUAL ({}°C)".format(temperatura_alvo)
                
            estado_ar = "LIGADO" if rele_ar.value() == 1 else "DESLIGADO"
            estado_luz = "LIGADA" if rele_luz.value() == 1 else "DESLIGADA"
            estado_cortina = "FECHADA" if rele_cortina.value() == 1 else "ABERTA"
            estado_alarme_texto = "ATIVADO" if alarme_ligado else "DESATIVADO"
            
            print("\n--- RESUMO DA CASA ---")
            print("Clima: {}°C | Gás: {}".format(temperatura, nivel_gas))
            print("Ar Condicionado: {} [{}]".format(estado_ar, modo_ar))
            print("Luz: {} | Cortina: {}".format(estado_luz, estado_cortina))
            print("Segurança (Alarme): {}".format(estado_alarme_texto))
            print("----------------------")

            pacote_de_dados = {
                "temperatura_atual": temperatura,
                "nivel_gas": nivel_gas,
                "movimento": movimento,
                "alarme_armado": alarme_ligado,
                "ar_ligado": rele_ar.value(),
                "janela_aberta": rele_janela.value(),
                "modo_ar_auto": modo_ar_auto,
                "ar_desligado_manual": ar_desligado_manual,
                "temperatura_alvo": temperatura_alvo
            }
            mensagem_texto = json.dumps(pacote_de_dados)
            mensageiro.publish(CANAL_ENVIAR_DADOS, mensagem_texto) 
            ultimo_aviso_enviado = agora

    except Exception as erro:
        print("Tropeço no sistema:", erro)
    
    time.sleep(0.2)