import os
import sys
import time
import traceback
from datetime import datetime

try:
    import winsound
except ImportError:
    winsound = None

# ---------- CONFIGURAÇÕES ----------
LARGURA = 45
SENHA_MESARIO = "1234"
MAX_TENTATIVAS = 3

# Sons (Windows): (frequência em Hz, duração em ms)
SOM_TECLA = (1200, 40)      # clique curto a cada tecla
SOM_CONFIRMA = (1000, 300)  # bipe médio ao confirmar cada voto
SOM_FINAL = (1000, 2000)    # bipe longo no FIM da votação
SOM_ERRO = (300, 250)       # tecla inválida

# Nomes e números FICTÍCIOS (misturas satíricas), para não favorecer ninguém.
CARGOS = [
    {
        "nome": "SENADOR",
        "digitos": 3,
        "candidatos": {
            "151": "Simone Damares Moro",
            "289": "Sérgio Marina Tebet",
            "573": "Guilherme Prado Francine",
            "846": "André Derrite Rufino",
        },
    },
    {
        "nome": "GOVERNADOR",
        "digitos": 2,
        "candidatos": {
            "17": "Tarcísio Zema Freitas",
            "33": "Romeu Haddad Gomes",
            "44": "Ronaldo Ratinho Caiado",
            "55": "Ciro Fernando de Souza",
        },
    },
    {
        "nome": "PRESIDENTE",
        "digitos": 2,
        "candidatos": {
            "23": "Luis Bolsonaro da Silva",
            "12": "Flavio Inácio Lula",
            "47": "Renan Cury",
            "31": "Augusto Santos",
        },
    },
]


# ---------- SONS ----------
def _tocar(som, bell_repeticoes=1):
    """Toca o som no Windows; nos outros sistemas usa o 'bell' do terminal."""
    if winsound:
        winsound.Beep(*som)
    else:
        for _ in range(bell_repeticoes):
            print("\a", end="", flush=True)
            if bell_repeticoes > 1:
                time.sleep(0.5)


def som_tecla():
    _tocar(SOM_TECLA)


def som_confirma():
    _tocar(SOM_CONFIRMA)


def som_final():
    _tocar(SOM_FINAL, bell_repeticoes=4)


def som_erro():
    _tocar(SOM_ERRO)


# ---------- TECLADO (leitura tecla a tecla, sem precisar de Enter) ----------
def ler_tecla():
    """Lê UMA tecla imediatamente, sem esperar Enter."""
    if not sys.stdin.isatty():
        tecla = sys.stdin.read(1)  # entrada redirecionada (testes)
    elif os.name == "nt":
        import msvcrt
        while True:
            tecla = msvcrt.getwch()
            if tecla in ("\x00", "\xe0"):  # teclas especiais (setas, F1...)
                msvcrt.getwch()
                continue
            break
    else:
        import termios
        import tty
        fd = sys.stdin.fileno()
        antigo = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            tecla = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, antigo)

    if tecla == "\x03":  # Ctrl+C
        raise KeyboardInterrupt
    if tecla == "":
        raise EOFError
    return tecla


def ler_senha(prompt):
    """Lê a senha tecla a tecla, mostrando * (não depende do getpass)."""
    print(prompt, end="", flush=True)
    senha = ""
    while True:
        tecla = ler_tecla()
        if tecla in ("\r", "\n"):
            print()
            return senha
        if tecla in ("\x08", "\x7f"):
            if senha:
                senha = senha[:-1]
                print("\b \b", end="", flush=True)
            continue
        if tecla.isprintable():
            senha += tecla
            som_tecla()
            print("*", end="", flush=True)


def pausar_saida():
    """Evita que a janela feche sozinha ao terminar (ou se houver erro)."""
    try:
        input("\nPressione ENTER para sair...")
    except (EOFError, KeyboardInterrupt):
        pass


# ---------- TELA ----------
def limpar_tela():
    os.system("cls" if os.name == "nt" else "clear")


def topo():
    print("=" * LARGURA)
    print("URNA ELETRÔNICA".center(LARGURA))
    print("ELEIÇÕES 2026".center(LARGURA))
    print("=" * LARGURA)


class UrnaEletronica:

    def __init__(self):
        self.cargos = CARGOS
        self.votos = {}
        for cargo in self.cargos:
            contagem = {num: 0 for num in cargo["candidatos"]}
            contagem["BRANCO"] = 0
            contagem["NULO"] = 0
            self.votos[cargo["nome"]] = contagem
        self.total_eleitores = 0

    # ---------- TELAS ----------
    def desenhar_tela(self, cargo, etapa, digitos, branco, aviso):
        n = cargo["digitos"]
        limpar_tela()
        topo()
        print(f"ETAPA {etapa} DE {len(self.cargos)} - {cargo['nome']}".center(LARGURA))
        print("=" * LARGURA)
        for numero, nome in cargo["candidatos"].items():
            print(f"  [{numero}] - {nome}")
        print("  [B] - Voto em Branco")
        print("=" * LARGURA)

        print(f"\n  SEU VOTO PARA {cargo['nome']}")
        if branco:
            campo = "BRANCO"
        else:
            campo = " ".join(list(digitos) + ["_"] * (n - len(digitos)))
        print(f"  Nº: {campo}")

        if branco:
            info = "VOTO EM BRANCO"
        elif len(digitos) == n:
            nome = cargo["candidatos"].get(digitos)
            info = f"CANDIDATO: {nome}" if nome else "NÚMERO ERRADO - VOTO NULO"
        else:
            info = ""
        print(f"  {info}")
        if aviso:
            print(f"  ! {aviso}")

        print("\n" + "-" * LARGURA)
        print("  [0-9] Digita   [B] Branco   [C] Corrige")
        print("  [ENTER] CONFIRMA")
        if etapa == 1:
            print("  [M] Mesário (encerrar votação)")

    # ---------- VOTAÇÃO ----------
    def iniciar_votacao(self):
        while True:
            cedula = {}  # guarda as escolhas do eleitor antes de computar

            for etapa, cargo in enumerate(self.cargos, start=1):
                escolha = self.votar_cargo(cargo, etapa)
                if escolha == "ENCERRAR":
                    return
                cedula[cargo["nome"]] = escolha

            # Só computa depois que o eleitor concluiu todas as etapas
            for nome_cargo, escolha in cedula.items():
                self.votos[nome_cargo][escolha] += 1
            self.total_eleitores += 1
            self.finalizar_voto()

    def votar_cargo(self, cargo, etapa):
        n = cargo["digitos"]
        digitos = ""
        branco = False
        aviso = ""

        while True:
            self.desenhar_tela(cargo, etapa, digitos, branco, aviso)
            aviso = ""
            tecla = ler_tecla()
            letra = tecla.upper()

            if tecla in "0123456789":
                if branco or len(digitos) >= n:
                    som_erro()
                    aviso = "Aperte CORRIGE (C) para refazer."
                else:
                    digitos += tecla
                    som_tecla()

            elif letra == "B":
                if digitos == "" and not branco:
                    branco = True
                    som_tecla()
                else:
                    som_erro()
                    aviso = "BRANCO só com o campo vazio. Aperte C."

            elif letra == "C" or tecla in ("\x08", "\x7f"):
                digitos = ""
                branco = False
                som_tecla()

            elif tecla in ("\r", "\n"):
                if branco:
                    som_confirma()
                    return "BRANCO"
                if len(digitos) == n:
                    som_confirma()
                    return digitos if digitos in cargo["candidatos"] else "NULO"
                som_erro()
                aviso = f"Digite os {n} dígitos antes de confirmar."

            elif letra == "M" and etapa == 1 and digitos == "" and not branco:
                som_tecla()
                if self.validar_mesario():
                    return "ENCERRAR"
                aviso = "Acesso negado."

            else:
                som_erro()

    def finalizar_voto(self):
        limpar_tela()
        print("\n" + "=" * LARGURA)
        print("F I M".center(LARGURA))
        print("=" * LARGURA)
        som_final()
        time.sleep(0.5)

    # ---------- MESÁRIO ----------
    def validar_mesario(self):
        for tentativa in range(1, MAX_TENTATIVAS + 1):
            senha = ler_senha(f"\nSenha do mesário ({tentativa}/{MAX_TENTATIVAS}): ")
            if senha == SENHA_MESARIO:
                return True
            print("Senha incorreta!")
            som_erro()
        return False

    # ---------- BOLETIM DE URNA ----------
    def gerar_boletim(self):
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        linhas = [
            "=" * LARGURA,
            "BOLETIM DE URNA".center(LARGURA),
            "ELEIÇÕES 2026".center(LARGURA),
            "=" * LARGURA,
            f"Data/Hora: {agora}",
            f"Total de eleitores: {self.total_eleitores}",
        ]

        if self.total_eleitores == 0:
            linhas.append("-" * LARGURA)
            linhas.append("Nenhum voto foi registrado no pleito.")
            linhas.append("=" * LARGURA)
            return linhas

        total = self.total_eleitores

        def pct(qtd):
            return (qtd / total) * 100

        for cargo in self.cargos:
            contagem = self.votos[cargo["nome"]]
            linhas.append("=" * LARGURA)
            linhas.append(f"{cargo['nome']}".center(LARGURA))
            linhas.append("-" * LARGURA)

            for num, nome in cargo["candidatos"].items():
                qtd = contagem[num]
                linhas.append(f"• {nome} ({num}): {qtd} voto(s) ({pct(qtd):.1f}%)")

            b, n = contagem["BRANCO"], contagem["NULO"]
            linhas.append(f"• Votos em Branco: {b} ({pct(b):.1f}%)")
            linhas.append(f"• Votos Nulos: {n} ({pct(n):.1f}%)")
            linhas.append("-" * LARGURA)

            maior = max(contagem[num] for num in cargo["candidatos"])
            vencedores = [
                nome for num, nome in cargo["candidatos"].items()
                if contagem[num] == maior
            ]

            if maior == 0:
                linhas.append("Resultado: Não houve votos válidos em candidatos.")
            elif len(vencedores) == 1:
                linhas.append(f"{cargo['nome']} ELEITO: {vencedores[0]}!")
            else:
                linhas.append(f"EMPATE ENTRE: {', '.join(vencedores)}")

        linhas.append("=" * LARGURA)
        return linhas

    def salvar_boletim(self, linhas):
        nome_arquivo = datetime.now().strftime("boletim_urna_%Y%m%d_%H%M%S.txt")
        with open(nome_arquivo, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n")
        return nome_arquivo

    def exibir_resultado(self):
        limpar_tela()
        topo()
        print("APURAÇÃO DOS VOTOS".center(LARGURA))
        linhas = self.gerar_boletim()
        print("\n".join(linhas))

        try:
            arquivo = self.salvar_boletim(linhas)
            print(f"\nBoletim salvo em: {arquivo}")
        except OSError as erro:
            print(f"\nNão foi possível salvar o boletim: {erro}")


if __name__ == "__main__":
    urna = UrnaEletronica()
    try:
        urna.iniciar_votacao()
        urna.exibir_resultado()
    except (KeyboardInterrupt, EOFError):
        print("\n\nVotação interrompida.")
    except Exception:
        print("\n\nOcorreu um erro no programa:\n")
        traceback.print_exc()
    pausar_saida()