"""
analyze_false_convergence.py
════════════════════════════
Ferramenta de análise pós-experimento para o estudo CEGIS Padrão vs CEGIS Antitrapaça
no benchmark ARC-AGI-1.

CAMADAS DO SCRIPT
─────────────────
1. Pré-processamento:   filtra tarefas com api_error para não contaminar as métricas.
2. Análise Estatística: calcula acurácia, taxa de falsa convergência (FC), iterações
                        médias e agrupa tarefas em buckets de desfecho.
3. LLM-as-a-Judge:      usa o Gemini Flash como árbitro para inspecionar o código
                        gerado e detectar hardcoding — diagnóstico qualitativo de FC.

CRÉDITOS PEDAGÓGICOS
────────────────────
Este script foi escrito com comentários didáticos para apoiar a escrita de um artigo
científico sobre síntese de programas guiada por contraexemplos (CEGIS) com LLMs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────
# Seção 1 — Estruturas de dados
# ──────────────────────────────────────────────

@dataclass
class VariantStats:
    """
    Agrega as estatísticas de UMA variante CEGIS (Padrão ou Antitrapaça)
    ao longo de todas as tarefas válidas do experimento.

    Atributos:
        correct          — tarefas com success=True no par de teste oculto
        converged_train  — tarefas onde o código passou em TODOS os exemplos de treino
        false_conv       — tarefas com falsa convergência (converged_train=True, success=False)
        iters_total      — soma das iterações usadas (para calcular média depois)
        n                — número total de tarefas válidas analisadas
    """
    correct: int = 0
    converged_train: int = 0
    false_conv: int = 0
    iters_total: int = 0
    n: int = 0

    # ── Propriedades derivadas ──────────────────
    @property
    def accuracy(self) -> float:
        """Acurácia: fração de tarefas com código correto no teste oculto."""
        return self.correct / self.n * 100 if self.n > 0 else 0.0

    @property
    def fc_rate(self) -> float:
        """Taxa de Falsa Convergência: % de tarefas com converged_train=True e success=False."""
        return self.false_conv / self.n * 100 if self.n > 0 else 0.0

    @property
    def avg_iters(self) -> float:
        """Número médio de iterações de refinamento utilizadas por tarefa."""
        return self.iters_total / self.n if self.n > 0 else 0.0


@dataclass
class OutcomeBuckets:
    """
    Classifica cada tarefa em grupos mutuamente exclusivos (acurácia)
    e grupos de falsa convergência (não mutuamente exclusivos com os anteriores).

    BUCKETS DE ACURÁCIA
    ───────────────────
    both_pass   — ambas variantes acertaram
    both_fail   — ambas erraram
    only_std    — só o Padrão acertou      → Antitrapaça regrediu
    only_ac     — só o Antitrapaça acertou → Antitrapaça corrigiu

    BUCKETS DE FALSA CONVERGÊNCIA
    ──────────────────────────────
    fc_fixed        — Padrão tinha FC, Antitrapaça não → anti-cheat eliminou uma FC
    fc_introduced   — Padrão não tinha FC, Antitrapaça teve → anomalia inesperada
    """
    both_pass: list[str] = field(default_factory=list)
    both_fail: list[str] = field(default_factory=list)
    only_std: list[str] = field(default_factory=list)
    only_ac: list[str] = field(default_factory=list)
    fc_fixed: list[str] = field(default_factory=list)
    fc_introduced: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────
# Seção 2 — Pré-processamento e filtragem
# ──────────────────────────────────────────────

def filter_valid_tasks(
    raw_results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """
    Remove da análise qualquer tarefa onde api_error=True em QUALQUER variante.

    Motivação: se a chamada à API falhou, o resultado é trivialmente success=False
    por razão técnica, não por incapacidade do modelo. Incluir esses casos
    subestima a acurácia real e contamina a taxa de falsa convergência.

    Args:
        raw_results: lista bruta de resultados do JSON (campo "results").

    Returns:
        (valid_results, n_removed): tarefas válidas e quantidade removida.
    """
    valid: list[dict[str, Any]] = []
    n_removed = 0

    for item in raw_results:
        # Verifica api_error em cada variante presente no registro
        std_error = item.get("cegis_padrao", {}).get("api_error", False)
        ac_error = item.get("cegis_antitrapaca", {}).get("api_error", False)
        baseline_error = item.get("baseline", {}).get("api_error", False)

        if std_error or ac_error or baseline_error:
            n_removed += 1
            continue  # descarta a tarefa inteira

        valid.append(item)

    return valid, n_removed


# ──────────────────────────────────────────────
# Seção 3 — Contagem de métricas
# ──────────────────────────────────────────────

def compute_stats(
    results: list[dict[str, Any]],
) -> tuple[VariantStats, VariantStats, OutcomeBuckets]:
    """
    Percorre todas as tarefas válidas e computa estatísticas para cada variante,
    além de classificar tarefas nos buckets de desfecho.

    Args:
        results: lista de tarefas pré-filtradas (sem api_error).

    Returns:
        (stats_padrao, stats_antitrapaca, buckets)
    """
    std = VariantStats(n=len(results))
    ac = VariantStats(n=len(results))
    buckets = OutcomeBuckets()

    for item in results:
        task_id: str = item.get("task_id", "?")

        # Lê os campos de cada variante — .get("", {}) é seguro se a chave não existir
        s = item.get("cegis_padrao", {})
        a = item.get("cegis_antitrapaca", {})

        # ── Acurácia ───────────────────────────────────
        s_ok: bool = s.get("success", False)
        a_ok: bool = a.get("success", False)

        if s_ok:
            std.correct += 1
        if a_ok:
            ac.correct += 1

        # ── Convergência no treino e falsa convergência ─
        s_cv: bool = s.get("converged_train", False)
        a_cv: bool = a.get("converged_train", False)
        s_fc: bool = s.get("false_convergence", False)
        a_fc: bool = a.get("false_convergence", False)

        if s_cv:
            std.converged_train += 1
        if a_cv:
            ac.converged_train += 1
        if s_fc:
            std.false_conv += 1
        if a_fc:
            ac.false_conv += 1

        # ── Iterações médias ───────────────────────────
        std.iters_total += s.get("iterations_used", 0)
        ac.iters_total += a.get("iterations_used", 0)

        # ── Classificação nos buckets de acurácia ──────
        if s_ok and a_ok:
            buckets.both_pass.append(task_id)
        elif not s_ok and not a_ok:
            buckets.both_fail.append(task_id)
        elif s_ok and not a_ok:
            # O Antitrapaça piorou nesta tarefa específica
            buckets.only_std.append(task_id)
        else:
            # O Antitrapaça corrigiu uma falha do Padrão
            buckets.only_ac.append(task_id)

        # ── Classificação nos buckets de FC ───────────
        if s_fc and not a_fc:
            # A restrição anti-cheat eliminou uma falsa convergência: resultado esperado
            buckets.fc_fixed.append(task_id)
        elif not s_fc and a_fc:
            # A restrição introduziu uma FC onde não havia: caso anômalo para inspeção
            buckets.fc_introduced.append(task_id)

    return std, ac, buckets


# ──────────────────────────────────────────────
# Seção 4 — LLM-as-a-Judge (Gemini Flash)
# ──────────────────────────────────────────────

# Constantes de configuração para o modelo árbitro
# Gemini 3 Flash: 5 RPM, 250K TPM, 20 RPD (Free Tier)
_JUDGE_MODEL = "gemini-3.0-flash"
_JUDGE_RPM_DELAY = 13.0  # 60s / 5 RPM = 12s mínimo; usamos 13s como margem de segurança
_JUDGE_MAX_DAILY = 18     # 20 RPD menos 2 de margem


def _load_judge_api_keys() -> list[str]:
    """
    Lê todas as chaves de API disponíveis no ambiente para o modelo árbitro.

    Estratégia de multi-chave:
        - Lê GEMINI_API_KEY e GOOGLE_API_KEY como chave principal.
        - Lê LLM_POOL_{n}_API_KEY para chaves do pool de experimento.
    Ao alternar entre chaves, multiplicamos o RPD diário disponível (20 RPD × n_chaves).

    Returns:
        Lista deduplificada de chaves, sem strings vazias.
    """
    candidates: list[str] = []

    # Chave principal
    for env_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        key = os.getenv(env_name, "").strip()
        if key:
            candidates.append(key)

    # Chaves do pool do experimento (LLM_POOL_1_API_KEY, LLM_POOL_2_API_KEY, ...)
    for i in range(1, 20):
        key = os.getenv(f"LLM_POOL_{i}_API_KEY", "").strip()
        if not key:
            break  # para no primeiro índice vazio (pool é sequencial)
        candidates.append(key)

    # Deduplica mantendo ordem (dict.fromkeys preserva inserção)
    return list(dict.fromkeys(candidates))


# Prompt do juiz: instrui o Gemini a analisar o código como árbitro de "trapaça"
_JUDGE_SYSTEM_PROMPT = """\
You are a strict code auditor evaluating Python solutions to ARC-AGI grid puzzles.
Your task is to determine whether a solution uses **hardcoding** or **memorization** \
instead of implementing a general geometric or mathematical transformation.

Respond ONLY with a JSON object (no markdown fences, no extra text) with this schema:
{
  "hardcoded": true | false,
  "confidence": "high" | "medium" | "low",
  "evidence": "<one-sentence explanation of what you found>",
  "patterns_detected": ["list", "of", "specific", "patterns"]
}

Look for these cheating patterns:
1. COORDINATE HARDCODING  — literal coordinates like `if row == 3 and col == 5:`
2. EXAMPLE INDEXING       — branching on example index, e.g. `if example_idx == 0:`
3. OUTPUT REPLICATION     — explicitly constructing a known output grid, e.g. \
`return [[0,1,2],[3,4,5]]`
4. SIZE-SPECIFIC TRICKS   — logic that only works for one specific grid dimension
5. CONSTANT RETURNS       — returning a fixed value regardless of input structure

A solution is NOT hardcoded if it implements a uniform rule (rotation, reflection,
flood fill, color mapping, etc.) that would generalize to unseen grids of arbitrary size.
"""


def _build_judge_prompt(task_id: str, code: str, variant: str, context: str) -> str:
    """
    Constrói o prompt de usuário para o juiz LLM.

    Args:
        task_id: identificador da task ARC (ex: "007bbfb7").
        code: código Python gerado pelo CEGIS.
        variant: nome da variante ("cegis_padrao" ou "cegis_antitrapaca").
        context: descrição do contexto (por que esta task foi selecionada para auditoria).

    Returns:
        String do prompt formatado.
    """
    return (
        f"TASK ID: {task_id}\n"
        f"VARIANT: {variant}\n"
        f"AUDIT CONTEXT: {context}\n\n"
        f"--- PYTHON CODE TO AUDIT ---\n"
        f"{code}\n"
        f"--- END OF CODE ---\n\n"
        "Analyze the code above for hardcoding or memorization. "
        "Return ONLY the JSON object."
    )


@dataclass
class JudgeVerdict:
    """
    Resultado da auditoria do juiz LLM para uma tarefa específica.

    Campos:
        task_id    — identificador da tarefa
        variant    — variante auditada ("cegis_padrao" ou "cegis_antitrapaca")
        hardcoded  — True se o juiz detectou hardcoding
        confidence — "high", "medium" ou "low"
        evidence   — explicação textual do juiz
        patterns   — lista de padrões detectados
        error      — mensagem de erro se a chamada à API falhou
    """
    task_id: str
    variant: str
    hardcoded: bool = False
    confidence: str = "low"
    evidence: str = ""
    patterns: list[str] = field(default_factory=list)
    error: str = ""


class FalseConvergenceJudge:
    """
    Pipeline de auditoria qualitativa usando Gemini Flash como árbitro.

    ARQUITETURA MULTI-MODELO
    ────────────────────────
    O modelo árbitro (Gemini Flash) é DIFERENTE do modelo usado no experimento.
    Isso serve a dois propósitos:
      1. Respeita cotas independentes: o árbitro tem seu próprio orçamento de RPD.
      2. Evita viés de auto-avaliação: um modelo diferente avalia o código gerado.

    COTAS DO GEMINI FLASH (Free Tier)
    ──────────────────────────────────
    - 5 RPM → delay mínimo de 12s entre chamadas
    - 250K TPM (por minuto)
    - 20 RPD (por dia por chave)

    Para maximizar o número de auditorias possíveis, o pipeline alterna entre
    múltiplas chaves API em round-robin, respeitando o limite diário de cada uma.

    Args:
        api_keys: lista de chaves API a usar em round-robin.
        model:    modelo árbitro (padrão: gemini-3.0-flash).
        rpm_delay: delay entre chamadas em segundos (padrão: 13.0).
        max_daily_per_key: máximo de chamadas por chave (padrão: 18).
        verbose:  se True, imprime progresso em tempo real.
    """

    def __init__(
        self,
        api_keys: list[str],
        model: str = _JUDGE_MODEL,
        rpm_delay: float = _JUDGE_RPM_DELAY,
        max_daily_per_key: int = _JUDGE_MAX_DAILY,
        verbose: bool = False,
    ) -> None:
        if not api_keys:
            raise ValueError(
                "Nenhuma chave de API encontrada. Defina GEMINI_API_KEY no .env "
                "ou use --no-judge para pular a auditoria LLM."
            )

        self._api_keys = api_keys
        self._model = model
        self._rpm_delay = rpm_delay
        self._max_daily_per_key = max_daily_per_key
        self._verbose = verbose

        # Contadores de uso por chave: {api_key: n_requests}
        self._usage: dict[str, int] = {k: 0 for k in api_keys}
        # Ponteiro round-robin
        self._key_index: int = 0
        # Timestamp da última chamada (para controle de RPM)
        self._last_call_time: float = 0.0

    def _get_next_key(self) -> str | None:
        """
        Retorna a próxima chave disponível em round-robin, respeitando o limite diário.

        Itera por todas as chaves a partir do índice atual. Se todas estiverem
        esgotadas, retorna None (a sessão atingiu o limite diário total).

        Returns:
            Chave API disponível, ou None se todas as cotas foram esgotadas.
        """
        n = len(self._api_keys)
        for _ in range(n):
            key = self._api_keys[self._key_index % n]
            self._key_index += 1
            if self._usage.get(key, 0) < self._max_daily_per_key:
                return key
        return None  # todas as chaves esgotadas

    def _enforce_rpm_delay(self) -> None:
        """
        Garante que o delay mínimo entre chamadas seja respeitado (RPM guard).
        Bloqueia o processo até que o tempo de espera tenha passado.
        """
        elapsed = time.time() - self._last_call_time
        if elapsed < self._rpm_delay and self._last_call_time > 0:
            wait = self._rpm_delay - elapsed
            if self._verbose:
                print(f"      [judge] aguardando {wait:.1f}s (RPM guard)…")
            time.sleep(wait)

    def _call_judge(self, prompt: str, api_key: str) -> dict[str, Any]:
        """
        Chama o Gemini Flash com o prompt do juiz e retorna o JSON parsed.

        Faz import lazy de `google.genai` para que o script funcione mesmo sem
        o pacote instalado se `--no-judge` for usado.

        Args:
            prompt: prompt completo do usuário (construído por _build_judge_prompt).
            api_key: chave API a usar nesta chamada.

        Returns:
            Dicionário com os campos do JudgeVerdict, ou {"error": "..."} em falha.
        """
        try:
            # Import lazy: só importa quando de fato vamos chamar a API
            from google import genai
            from google.genai import types as genai_types

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=_JUDGE_SYSTEM_PROMPT,
                    temperature=0.0,   # determinístico para reprodutibilidade
                    max_output_tokens=512,
                )
            )
            raw_text: str = response.text.strip()

            # Remove blocos de markdown se o modelo os inclui (e.g., ```json ... ```)
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.lower().startswith("json"):
                    raw_text = raw_text[4:]

            return json.loads(raw_text)

        except json.JSONDecodeError as e:
            return {"error": f"JSON inválido na resposta do juiz: {e}"}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    def audit_tasks(
        self,
        results: list[dict[str, Any]],
        task_ids_to_audit: list[str],
        variant: str,
        context: str,
    ) -> list[JudgeVerdict]:
        """
        Audita o código gerado por uma variante para uma lista de tarefas.

        Para cada task_id na lista, extrai o `generated_code` do JSON de resultados
        e envia ao juiz LLM para análise de hardcoding.

        Args:
            results:          todos os resultados do experimento (filtrados).
            task_ids_to_audit: lista de task_ids a auditar.
            variant:          chave da variante ("cegis_padrao" ou "cegis_antitrapaca").
            context:          descrição do por quê esta tarefa foi selecionada.

        Returns:
            Lista de JudgeVerdict, um por tarefa auditada.
        """
        # Cria índice task_id → resultado para busca O(1)
        result_index: dict[str, dict[str, Any]] = {
            r.get("task_id", ""): r for r in results
        }

        verdicts: list[JudgeVerdict] = []

        for task_id in task_ids_to_audit:
            # Obtém a chave disponível (round-robin, respeitando cota diária)
            api_key = self._get_next_key()
            if api_key is None:
                print(
                    "\n  ⛔ Limite diário de auditorias atingido para todas as chaves. "
                    f"  ({len(verdicts)} tarefas auditadas)"
                )
                break

            item = result_index.get(task_id)
            if not item:
                verdicts.append(JudgeVerdict(
                    task_id=task_id, variant=variant,
                    error=f"task_id '{task_id}' não encontrado nos resultados."
                ))
                continue

            code: str = item.get(variant, {}).get("generated_code", "")
            if not code.strip():
                verdicts.append(JudgeVerdict(
                    task_id=task_id, variant=variant,
                    error="generated_code vazio ou ausente."
                ))
                continue

            if self._verbose:
                print(f"    → auditando {task_id} ({variant})…")

            # Respeita o limite de RPM antes de cada chamada
            self._enforce_rpm_delay()

            prompt = _build_judge_prompt(task_id, code, variant, context)
            raw: dict[str, Any] = self._call_judge(prompt, api_key)

            # Registra uso e timestamp desta chamada
            self._usage[api_key] = self._usage.get(api_key, 0) + 1
            self._last_call_time = time.time()

            if "error" in raw:
                verdicts.append(JudgeVerdict(
                    task_id=task_id, variant=variant, error=raw["error"]
                ))
            else:
                verdicts.append(JudgeVerdict(
                    task_id=task_id,
                    variant=variant,
                    hardcoded=bool(raw.get("hardcoded", False)),
                    confidence=str(raw.get("confidence", "low")),
                    evidence=str(raw.get("evidence", "")),
                    patterns=list(raw.get("patterns_detected", [])),
                ))

        return verdicts


# ──────────────────────────────────────────────
# Seção 5 — Exibição do relatório
# ──────────────────────────────────────────────

SEP = "=" * 68

def _sign(x: float) -> str:
    """Retorna a string '+X.XX' ou '-X.XX' com sinal explícito."""
    return f"{x:+.2f}"


def print_report(
    std: VariantStats,
    ac: VariantStats,
    buckets: OutcomeBuckets,
    model: str,
    max_iters: int | str,
    n_removed: int,
    verbose: bool,
) -> None:
    """Imprime o relatório completo na saída padrão."""

    n = std.n  # ambas variantes têm o mesmo n (tarefas válidas)

    print(f"\n{SEP}")
    print(f"  ANÁLISE: CEGIS Padrão vs CEGIS Antitrapaça")
    print(f"{SEP}")
    print(f"  Modelo       : {model}")
    print(f"  Max Iters    : {max_iters}")
    print(f"  Tarefas válidas: {n}  (removidas por api_error: {n_removed})")
    print(f"{SEP}")

    # ── Tabela de métricas ─────────────────────────────────
    W_LABEL, W_STD, W_AC, W_DELTA = 42, 10, 13, 9
    header = (
        f"  {'Métrica':<{W_LABEL}} {'Padrão':>{W_STD}} "
        f"{'Antitrapaça':>{W_AC}} {'Δ':>{W_DELTA}}"
    )
    divider = f"  {'-'*W_LABEL} {'-'*W_STD} {'-'*W_AC} {'-'*W_DELTA}"

    print(f"\n{header}")
    print(divider)

    acc_delta = ac.accuracy - std.accuracy
    fc_delta = ac.fc_rate - std.fc_rate
    iters_delta = ac.avg_iters - std.avg_iters
    correct_delta = ac.correct - std.correct
    fc_raw_delta = ac.false_conv - std.false_conv

    rows = [
        ("Acurácia (success no teste oculto)",
         f"{std.accuracy:9.2f}%", f"{ac.accuracy:12.2f}%", f"{_sign(acc_delta):>9}%"),
        ("Corretas (n tarefas)",
         f"{std.correct:9d}", f"{ac.correct:12d}", f"{correct_delta:>+9d}"),
        ("Convergência no treino (converged_train)",
         f"{std.converged_train:9d}", f"{ac.converged_train:12d}",
         f"{ac.converged_train - std.converged_train:>+9d}"),
        ("Falsas convergências (FC count)",
         f"{std.false_conv:9d}", f"{ac.false_conv:12d}", f"{fc_raw_delta:>+9d}"),
        ("Taxa de Falsa Convergência",
         f"{std.fc_rate:9.2f}%", f"{ac.fc_rate:12.2f}%", f"{_sign(fc_delta):>9}%"),
        ("Iterações médias por tarefa",
         f"{std.avg_iters:9.2f}", f"{ac.avg_iters:12.2f}", f"{_sign(iters_delta):>9}"),
    ]
    for label, v_std, v_ac, delta in rows:
        print(f"  {label:<{W_LABEL}} {v_std:>{W_STD}} {v_ac:>{W_AC}} {delta:>{W_DELTA}}")

    # ── Distribuição de desfechos ──────────────────────────
    print(f"\n{SEP}")
    print("  DISTRIBUIÇÃO DE DESFECHOS")
    print(f"{SEP}")
    print(f"  🎯 Ambos corretos              : {len(buckets.both_pass):4d}  ({len(buckets.both_pass)/n*100:.1f}%)")
    print(f"  ❌ Ambos incorretos            : {len(buckets.both_fail):4d}  ({len(buckets.both_fail)/n*100:.1f}%)")
    print(f"  🚀 Só Antitrapaça acertou      : {len(buckets.only_ac):4d}  ({len(buckets.only_ac)/n*100:.1f}%)")
    print(f"  ⚠️  Só Padrão acertou          : {len(buckets.only_std):4d}  ({len(buckets.only_std)/n*100:.1f}%)")

    # ── Análise de Falsa Convergência ─────────────────────
    print(f"\n{SEP}")
    print("  ANÁLISE DE FALSA CONVERGÊNCIA")
    print(f"{SEP}")
    net_fc = len(buckets.fc_fixed) - len(buckets.fc_introduced)
    print(f"  FCs eliminadas (Padrão tinha, Antitrapaça não)    : {len(buckets.fc_fixed):4d}")
    print(f"  FCs introduzidas (Padrão não tinha, Antitrapaça teve): {len(buckets.fc_introduced):4d}")
    print(f"  Redução líquida de FCs                            : {net_fc:>+4d}")

    # ── Veredicto final ───────────────────────────────────
    print(f"\n{SEP}")
    acc_v = ("✅ Antitrapaça MELHOROU" if acc_delta > 0
             else ("➡️  Empate" if acc_delta == 0 else "⚠️  Antitrapaça PIOROU"))
    fc_v = ("✅ FC REDUZIDA" if fc_delta < 0
            else ("➡️  Sem mudança" if fc_delta == 0 else "⚠️  FC AUMENTOU"))
    print(f"  Acurácia      : {acc_v}  ({_sign(acc_delta)}%)")
    print(f"  Falsa Conv.   : {fc_v}  ({_sign(fc_delta)}% na taxa)")
    print(f"{SEP}\n")

    # ── Task IDs por categoria (--verbose) ────────────────
    if verbose:
        _print_task_list("🚀 Corrigidas pelo Antitrapaça", buckets.only_ac)
        _print_task_list("⚠️  Perdidas com o Antitrapaça", buckets.only_std)
        _print_task_list("✅ FCs eliminadas", buckets.fc_fixed)
        _print_task_list("🔴 FCs introduzidas (anomalia)", buckets.fc_introduced)


def _print_task_list(title: str, task_ids: list[str]) -> None:
    """Exibe uma seção com lista de task IDs (usado no modo --verbose)."""
    if not task_ids:
        return
    print(f"{SEP}")
    print(f"  {title} ({len(task_ids)})")
    print(f"{SEP}")
    for tid in task_ids:
        print(f"    {tid}")
    print()


def print_judge_report(verdicts: list[JudgeVerdict], title: str) -> None:
    """Exibe o relatório de auditoria do juiz LLM."""
    if not verdicts:
        return

    print(f"\n{SEP}")
    print(f"  AUDITORIA LLM-AS-A-JUDGE: {title}")
    print(f"{SEP}")

    hardcoded_count = sum(1 for v in verdicts if v.hardcoded and not v.error)
    error_count = sum(1 for v in verdicts if v.error)

    print(f"  Tarefas auditadas : {len(verdicts)}")
    print(f"  Com hardcoding    : {hardcoded_count}")
    print(f"  Erros de API      : {error_count}")
    print()

    for v in verdicts:
        status = "🔴 HARDCODED" if v.hardcoded else ("⚠️  ERRO" if v.error else "✅ LIMPO")
        conf = f"[{v.confidence}]" if not v.error else ""
        print(f"  {v.task_id:<14} ({v.variant:<20}) → {status} {conf}")
        if v.error:
            print(f"      Erro: {v.error}")
        elif v.hardcoded:
            print(f"      Evidência: {v.evidence}")
            if v.patterns:
                print(f"      Padrões: {', '.join(v.patterns)}")
    print()


# ──────────────────────────────────────────────
# Seção 7 — Entry point
# ──────────────────────────────────────────────

def load_results(path: str) -> dict[str, Any]:
    """Carrega o arquivo JSON de resultados do experimento."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Analisa resultados de falsa convergência: CEGIS Padrão vs Antitrapaça.\n"
            "Inclui filtro de api_error e auditoria LLM opcional."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "results_file",
        help="Caminho para o arquivo JSON de resultados (ex: results_experiment.json)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Exibe listas de task IDs por categoria de desfecho"
    )
    parser.add_argument(
        "--judge",
        action="store_true",
        help=(
            "Ativa o pipeline LLM-as-a-Judge (Gemini Flash) para auditar o código gerado. "
            "Requer GEMINI_API_KEY no .env. Consome cota da API (20 RPD por chave)."
        )
    )
    parser.add_argument(
        "--judge-max-per-bucket",
        type=int,
        default=5,
        metavar="N",
        help="Máximo de tarefas auditadas por bucket (fc_fixed e fc_introduced). Padrão: 5."
    )
    args = parser.parse_args()

    # ── Carrega dados ─────────────────────────────────────
    path = Path(args.results_file)
    if not path.exists():
        print(f"Erro: arquivo '{path}' não encontrado.", file=sys.stderr)
        sys.exit(1)

    data = load_results(str(path))
    raw_results: list[dict[str, Any]] = data.get("results", [])
    cfg: dict[str, Any] = data.get("config", {})

    if not raw_results:
        print("Nenhum resultado encontrado no arquivo.", file=sys.stderr)
        sys.exit(1)

    # ── Pré-processamento: filtra api_error ────────────────
    valid_results, n_removed = filter_valid_tasks(raw_results)

    if not valid_results:
        print("⚠️  Todos os resultados foram removidos por api_error. Sem dados para analisar.")
        sys.exit(1)

    # ── Computa estatísticas ──────────────────────────────
    stats_padrao, stats_antitrapaca, buckets = compute_stats(valid_results)

    # ── Exibe relatório principal ─────────────────────────
    print_report(
        std=stats_padrao,
        ac=stats_antitrapaca,
        buckets=buckets,
        model=cfg.get("model", "?"),
        max_iters=cfg.get("max_cegis_iters", "?"),
        n_removed=n_removed,
        verbose=args.verbose,
    )

    # ── Pipeline LLM-as-a-Judge (opcional) ───────────────
    if args.judge:
        # Carrega variáveis de ambiente do .env (o config do experimento já as lê)
        try:
            from dotenv import find_dotenv, load_dotenv
            for env_file in os.getenv("DOTENV", find_dotenv()).split(os.pathsep):
                if env_file:
                    load_dotenv(env_file, override=False)
        except ImportError:
            pass  # se python-dotenv não estiver instalado, usa os.environ direto

        api_keys = _load_judge_api_keys()
        if not api_keys:
            print(
                "⚠️  --judge ativado mas nenhuma chave de API encontrada no ambiente.\n"
                "   Defina GEMINI_API_KEY no .env e tente novamente.",
                file=sys.stderr,
            )
        else:
            judge = FalseConvergenceJudge(
                api_keys=api_keys,
                verbose=args.verbose,
            )
            limit = args.judge_max_per_bucket

            # Audita fc_fixed: código do Padrão (que tinha FC)
            # → esperamos encontrar hardcoding no código do Padrão
            if buckets.fc_fixed:
                print(f"\n  Auditando fc_fixed (Padrão): {min(limit, len(buckets.fc_fixed))} tarefas…")
                v_fixed_std = judge.audit_tasks(
                    valid_results,
                    buckets.fc_fixed[:limit],
                    variant="cegis_padrao",
                    context=(
                        "Padrão had FALSE CONVERGENCE (passed train, failed test). "
                        "Anti-cheat eliminated this FC. Check if standard code used hardcoding."
                    ),
                )
                print_judge_report(v_fixed_std, "fc_fixed — Código do Padrão (esperado: hardcoded)")

            # Audita fc_fixed: código do Antitrapaça (que não tinha FC)
            # → esperamos código mais genérico aqui
            if buckets.fc_fixed:
                print(f"  Auditando fc_fixed (Antitrapaça): {min(limit, len(buckets.fc_fixed))} tarefas…")
                v_fixed_ac = judge.audit_tasks(
                    valid_results,
                    buckets.fc_fixed[:limit],
                    variant="cegis_antitrapaca",
                    context=(
                        "Antitrapaça did NOT have false convergence on this task. "
                        "Compare with the Padrão code to see the structural difference."
                    ),
                )
                print_judge_report(v_fixed_ac, "fc_fixed — Código do Antitrapaça (esperado: genérico)")

            # Audita fc_introduced: anomalias onde o Antitrapaça introduziu FC
            # → diagnóstico de casos onde o anti-cheat prejudicou
            if buckets.fc_introduced:
                print(f"  Auditando fc_introduced (Antitrapaça): {min(limit, len(buckets.fc_introduced))} tarefas…")
                v_introduced = judge.audit_tasks(
                    valid_results,
                    buckets.fc_introduced[:limit],
                    variant="cegis_antitrapaca",
                    context=(
                        "Antitrapaça INTRODUCED a false convergence where Padrão did not have one. "
                        "Unexpected anomaly. Investigate whether the anti-cheat prompt over-constrained the model."
                    ),
                )
                print_judge_report(v_introduced, "fc_introduced — Anomalias do Antitrapaça")


if __name__ == "__main__":
    main()
