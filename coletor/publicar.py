# -*- coding: utf-8 -*-
"""
Publicação dos documentos.

  * Modo teste (padrão, `dry_run=True`): grava JSON em `saida/<colecao>.json`.
    Não precisa de Firebase e permite conferir tudo antes de publicar.
  * Modo real (`dry_run=False`): grava no Firestore via Firebase Admin SDK,
    com a credencial em FIREBASE_SERVICE_ACCOUNT (JSON) ou serviceAccountKey.json.
    NÃO FOI TESTADO contra um Firestore real neste esqueleto: rode primeiro em
    um projeto de teste.

Regras de segurança no Firestore: leitura pública e NENHUMA escrita pelo cliente.
Só esta rotina (conta de serviço, que ignora as regras) escreve.
"""
import json
import logging
import os
from pathlib import Path

from .modelos import agora_iso

log = logging.getLogger(__name__)
LOTE = 400          # o Firestore aceita até 500 operações por lote


class Publicador:
    def __init__(self, dry_run=True, saida="saida"):
        self.dry_run = dry_run
        self.saida = Path(saida)
        self._db = None

    # ---------------- leitura da coleta anterior (para checar variação) -----
    def ler(self, colecao: str) -> dict:
        if self.dry_run:
            arq = self.saida / f"{colecao}.json"
            if not arq.exists():
                return {}
            return {d["id"]: d for d in json.loads(arq.read_text(encoding="utf-8"))}
        return {d.id: d.to_dict() for d in self._firestore().collection(colecao).stream()}

    # ---------------- escrita ---------------------------------------------
    def gravar(self, colecao: str, docs: list):
        if not docs:
            log.info("%s: nada a gravar", colecao)
            return
        if self.dry_run:
            self.saida.mkdir(parents=True, exist_ok=True)
            arq = self.saida / f"{colecao}.json"
            todos = self.ler(colecao)
            for d in docs:                                  # mescla CAMPO A CAMPO, como o merge=True do Firestore real
                todos[d["id"]] = {**todos.get(d["id"], {}), **d}
            arq.write_text(json.dumps(list(todos.values()), ensure_ascii=False, indent=2), encoding="utf-8")
            log.info("[teste] %s: %d documento(s) novos/atualizados (%d no total) em %s",
                     colecao, len(docs), len(todos), arq)
            return
        db = self._firestore()
        for i in range(0, len(docs), LOTE):
            lote = db.batch()
            for d in docs[i:i + LOTE]:
                lote.set(db.collection(colecao).document(d["id"]), d, merge=True)
            lote.commit()
        log.info("%s: %d documento(s) gravado(s) no Firestore", colecao, len(docs))

    def expirar(self, colecao: str, agora: str = None) -> int:
        """Remove vagas vencidas. Só deve ser chamado depois de uma coleta BEM-SUCEDIDA
        (se a coleta falhar, mantém-se o último conjunto válido)."""
        agora = agora or agora_iso()
        if self.dry_run:
            atuais = self.ler(colecao)
            vivos = [d for d in atuais.values() if d.get("expira_em", "9999") >= agora]
            removidos = len(atuais) - len(vivos)
            if removidos:
                arq = self.saida / f"{colecao}.json"
                arq.write_text(json.dumps(vivos, ensure_ascii=False, indent=2), encoding="utf-8")
            return removidos
        db = self._firestore()
        vencidos = [d for d in db.collection(colecao).stream() if (d.to_dict().get("expira_em") or "9999") < agora]
        for i in range(0, len(vencidos), LOTE):
            lote = db.batch()
            for d in vencidos[i:i + LOTE]:
                lote.delete(d.reference)
            lote.commit()
        return len(vencidos)

    def registrar_execucao(self, fonte: str, resumo: dict):
        """Guarda o resultado da última execução em `_coletas/<fonte>` (para monitoramento)."""
        registro = {"id": fonte, "executado_em": agora_iso(), **resumo}
        if self.dry_run:
            self.saida.mkdir(parents=True, exist_ok=True)
            (self.saida / f"_coleta_{fonte}.json").write_text(
                json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            self._firestore().collection("_coletas").document(fonte).set(registro)

    # ---------------- Firestore -------------------------------------------
    def verificar_credencial(self):
        """Falha cedo e com mensagem clara se for publicar sem credencial do Firebase."""
        if not self.dry_run:
            self._firestore()

    def _firestore(self):
        if self._db is not None:
            return self._db
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except ImportError as e:
            raise RuntimeError("Biblioteca firebase-admin não instalada (pip install -r requirements-coletor.txt)") from e

        if not firebase_admin._apps:
            bruto = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
            if bruto:
                cred = credentials.Certificate(json.loads(bruto))
            elif os.path.exists("serviceAccountKey.json"):
                cred = credentials.Certificate("serviceAccountKey.json")
            else:
                raise RuntimeError("Sem credencial: defina FIREBASE_SERVICE_ACCOUNT ou serviceAccountKey.json")
            firebase_admin.initialize_app(cred)
        self._db = firestore.client()
        return self._db
