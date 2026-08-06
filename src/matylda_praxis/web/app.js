"use strict";

const store = {
  records: [],
  current: null,
  tab: "workflow",
  query: "",
};

const stateOrder = ["seed", "incubator", "exploration", "working", "waiting", "cemetery"];
const stateLabels = {
  seed: "Seed",
  incubator: "Inkubator",
  exploration: "Eksploracja",
  working: "Robocza",
  waiting: "Poczekalnia",
  cemetery: "Cmentarz",
};
const eventLabels = {
  hypothesis_created: "Utworzono seed",
  state_advanced: "Zmieniono etap",
  preflight_completed: "Wykonano preflight",
  benchmark_recorded: "Zapisano benchmark",
  hostile_review_recorded: "Zapisano DARKROOM review",
  artifact_deflated: "Wykonano deflację",
  decision_recorded: "Zapisano decyzję człowieka",
  linked_run_created: "Utworzono nowy powiązany przebieg",
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHTML = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");
const textOrDash = (value) => value && String(value).trim() ? escapeHTML(value) : '<span class="muted">Brak</span>';
const listText = (items) => Array.isArray(items) && items.length ? items.join("\n") : "";
const lines = (value) => String(value || "").split("\n").map((item) => item.trim()).filter(Boolean);
const currentArtifact = (record) => record?.versions?.at(-1)?.artifact || {};

function effectiveState(record) {
  const memo = record?.decision_memos?.at(-1);
  if (memo?.decision === "WAIT") return "waiting";
  if (memo?.decision === "REJECT") return "cemetery";
  return record?.state || "seed";
}

function toast(message, type = "success") {
  const node = document.createElement("div");
  node.className = `toast ${type === "error" ? "error" : ""}`;
  node.textContent = message;
  $("#toast-stack").append(node);
  window.setTimeout(() => node.remove(), 4200);
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function loadRecords({ keepSelection = true } = {}) {
  try {
    const payload = await request("/hypotheses");
    store.records = payload.hypotheses;
    setConnection(true);
    renderList();
    if (keepSelection && store.current) {
      await selectRecord(store.current.id, false);
    } else if (!store.current && store.records.length) {
      await selectRecord(store.records[0].id, false);
    } else if (!store.records.length) {
      store.current = null;
      renderWorkspace();
    }
    return true;
  } catch (error) {
    setConnection(false);
    toast(error.message, "error");
    return false;
  }
}

function setConnection(online) {
  $("#connection-status").textContent = online ? "online" : "offline";
  $(".online-dot").classList.toggle("offline", !online);
}

async function selectRecord(id, renderLoading = true) {
  if (renderLoading) {
    $$(".hypothesis-row").forEach((row) => row.classList.toggle("active", row.dataset.id === id));
  }
  try {
    const payload = await request(`/hypotheses/${encodeURIComponent(id)}`);
    store.current = payload.hypothesis;
    renderList();
    renderWorkspace();
    return true;
  } catch (error) {
    toast(error.message, "error");
    return false;
  }
}

async function withBusyButton(button, task) {
  if (!button) return task();
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    return await task();
  } finally {
    if (button.isConnected) {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }
}

function renderList() {
  const query = store.query.trim().toLocaleLowerCase("pl");
  const records = store.records.filter((record) =>
    !query || record.title.toLocaleLowerCase("pl").includes(query) || record.id.toLowerCase().includes(query)
  );
  const counts = store.records.reduce((acc, record) => {
    const state = effectiveState(record);
    acc[state] = (acc[state] || 0) + 1;
    return acc;
  }, {});
  $("#state-summary").innerHTML = ["working", "waiting", "cemetery"]
    .filter((state) => counts[state])
    .map((state) => `<span class="summary-pill">${stateLabels[state]} <strong>${counts[state]}</strong></span>`)
    .join("");
  $("#hypothesis-list").innerHTML = records.length ? records.map((record) => {
    const state = effectiveState(record);
    return `<button class="hypothesis-row ${store.current?.id === record.id ? "active" : ""}" type="button" role="listitem" data-id="${escapeHTML(record.id)}">
      <span class="row-marker" aria-hidden="true"></span>
      <span class="row-main">
        <span class="row-title">${escapeHTML(record.title)}</span>
        <span class="row-meta"><span>${stateLabels[state]}</span><span>v${record.versions.at(-1).number}</span></span>
      </span>
    </button>`;
  }).join("") : `<div class="list-empty">${query ? "Brak pasujących zapisów" : "Rejestr jest pusty"}</div>`;
}

function renderWorkspace() {
  const hasRecord = Boolean(store.current);
  $("#empty-state").classList.toggle("hidden", hasRecord);
  $("#record-view").classList.toggle("hidden", !hasRecord);
  if (!hasRecord) return;
  const record = store.current;
  const state = effectiveState(record);
  $("#record-title").textContent = record.title;
  $("#record-id").textContent = record.id;
  $("#record-state").textContent = stateLabels[state];
  renderLifecycle(record, state);
  renderTabs();
}

function renderLifecycle(record, currentState) {
  let currentIndex = stateOrder.indexOf(currentState);
  if (record.disposition === "TEST" || record.disposition === "PUBLISH") currentIndex = 3;
  $("#lifecycle").innerHTML = stateOrder.map((state, index) => {
    let className = "life-step";
    if (index < currentIndex && currentState !== "cemetery") className += " done";
    if (state === currentState) className += " current";
    if (currentState === "cemetery" && ["seed", "incubator", "exploration", "working"].includes(state)) className += " done";
    return `<span class="${className}">${stateLabels[state]}</span>`;
  }).join("");
}

function renderTabs() {
  $$(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === store.tab));
  $$(".tab-panel").forEach((panel) => panel.classList.add("hidden"));
  $(`#panel-${store.tab}`).classList.remove("hidden");
  if (store.tab === "workflow") renderWorkflow();
  if (store.tab === "artifact") renderArtifact();
  if (store.tab === "evidence") renderEvidence();
  if (store.tab === "history") renderHistory();
}

function currentContext(record) {
  const version = record.versions.at(-1).number;
  const passingPreflight = [...record.preflight_checks].reverse().find((item) => item.artifact_version === version && item.issues.length === 0);
  const benchmark = [...record.benchmark_results].reverse().find((item) => item.artifact_version === version);
  const review = record.hostile_reviews.at(-1) || null;
  const deflation = record.deflations.at(-1) || null;
  const deflatedReady = Boolean(review && deflation && deflation.review_id === review.review_id && deflation.to_version === version);
  const benchmarkReview = Boolean(review && benchmark && review.benchmark_id === benchmark.benchmark_id && review.artifact_version === version);
  return { version, passingPreflight, benchmark, review, deflation, deflatedReady, benchmarkReview };
}

function workflowChecks(record, context) {
  const checks = [
    [record.state !== "seed", "Seed przyjęty do inkubatora"],
    [["exploration", "working", "waiting", "cemetery"].includes(record.state), "Pomysł przeszedł do eksploracji"],
    [record.versions.length > 1, "Istnieje jawny artefakt roboczy"],
    [Boolean(context.passingPreflight), "Deterministyczny preflight zaliczony"],
    [record.benchmark_results.length > 0, "Benchmark zapisany"],
    [record.hostile_reviews.length > 0, "DARKROOM zakończony"],
    [record.decision_memos.length > 0, "Człowiek podjął decyzję"],
  ];
  return `<aside class="workflow-aside"><h4>Ślad przebiegu</h4><ul class="check-list">${checks.map(([ok, label]) =>
    `<li><span class="${ok ? "ok" : "pending"}">${ok ? "&#10003;" : "&#183;"}</span><span>${label}</span></li>`
  ).join("")}</ul></aside>`;
}

function workflowShell(kicker, title, description, body) {
  const context = currentContext(store.current);
  return `<div class="workflow-layout"><div class="workflow-main">
    <span class="eyebrow">${kicker}</span><h3>${title}</h3><p>${description}</p>${body}
  </div>${workflowChecks(store.current, context)}</div>`;
}

function renderWorkflow() {
  const record = store.current;
  const state = effectiveState(record);
  const context = currentContext(record);
  let html = "";
  if (state === "waiting" || state === "cemetery") {
    html = resumeStep(state);
  } else if (record.decision_memos.length) {
    const memo = record.decision_memos.at(-1);
    html = workflowShell("DECISION MEMO", `Przebieg zakończony: ${memo.decision}`, "Decyzja jest zapisana i nie może zostać nadpisana. Wyniki testu lub publikacji należy zarejestrować w nowym, jawnie utworzonym cyklu badawczym.", `<div class="notice success">${escapeHTML(memo.rationale)}</div><button class="secondary-button" type="button" data-tab-jump="evidence">Zobacz łańcuch dowodowy</button>`);
  } else if (record.state === "seed") {
    html = simpleAdvance("INKUBATOR", "Zatrzymaj pomysł bez rozwijania", "Inkubator przechowuje obserwację, pytanie lub analogię bez żądania pełnej argumentacji.", "incubator", "Przenieś do inkubatora");
  } else if (record.state === "incubator") {
    html = simpleAdvance("EKSPLORACJA", "Sprawdź, czy warto poświęcić uwagę", "Przejście otwiera miejsce na zakres, założenia i najtańszy test. Nadal nie ogłasza twierdzenia.", "exploration", "Rozpocznij eksplorację");
  } else if (record.state === "exploration") {
    html = workingArtifactStep(currentArtifact(record));
  } else if (!context.passingPreflight) {
    html = preflightStep();
  } else if (context.deflatedReady) {
    html = decisionStep(context.review);
  } else if (!context.benchmark) {
    html = benchmarkStep();
  } else if (!context.benchmarkReview) {
    html = reviewStep(context.benchmark);
  } else if (context.review.recommendation === "REVISE" && !context.deflatedReady) {
    html = deflationStep(currentArtifact(record), context.review);
  } else {
    html = decisionStep(context.review);
  }
  $("#panel-workflow").innerHTML = html;
}

function simpleAdvance(kicker, title, description, state, label) {
  return workflowShell(kicker, title, description, `<button class="primary-button" type="button" data-advance="${state}">${label}</button>`);
}

function workingArtifactStep(artifact) {
  return workflowShell("ARTEFAKT ROBOCZY", "Nadaj hipotezie testowalny kształt", "Zakres, falsyfikacja i koszt są wymagane. Listy wpisuj po jednej pozycji w wierszu.", `
    <form class="protocol-form" data-form="working">
      <label>Wyjaśniający kandydat<textarea name="claim" required>${escapeHTML(artifact.claim)}</textarea></label>
      <label>Zakres<textarea name="scope" required>${escapeHTML(artifact.scope)}</textarea></label>
      <div class="form-grid">
        <label>Założenia<textarea name="assumptions">${escapeHTML(listText(artifact.assumptions))}</textarea></label>
        <label>Dowody za<textarea name="evidence_for">${escapeHTML(listText(artifact.evidence_for))}</textarea></label>
      </div>
      <label>Dowody przeciw<textarea name="evidence_against">${escapeHTML(listText(artifact.evidence_against))}</textarea></label>
      <label>Warunek falsyfikacji<textarea name="falsification_condition" required>${escapeHTML(artifact.falsification_condition)}</textarea></label>
      <label>Najmniejszy następny test<textarea name="next_test" required>${escapeHTML(artifact.next_test)}</textarea></label>
      <label>Oczekiwany koszt eksploracji<select name="exploration_cost" required>
        ${["5 min", "30 min", "half day", "2 days", "experiment", "new capability"].map((value) => `<option ${artifact.exploration_cost === value ? "selected" : ""}>${value}</option>`).join("")}
      </select></label>
      <button class="primary-button" type="submit">Utwórz working hypothesis</button>
    </form>`);
}

function preflightStep() {
  const latest = store.current.preflight_checks.at(-1);
  const failure = latest?.issues?.length ? `<div class="notice error">${latest.issues.map((item) => escapeHTML(item.message)).join("<br>")}</div>` : "";
  return workflowShell("PREFILTRY", "Uruchom deterministyczny preflight", "Sprawdzane są wymagane pola, koszt, aktywne duplikaty i pamięć negatywna. Model nie uczestniczy w tym kroku.", `${failure}<button class="primary-button" type="button" data-action="preflight">Uruchom preflight</button>`);
}

function benchmarkStep() {
  return workflowShell("BENCHMARK + LITERATURA", "Zapisz stan bazowy", "Benchmark ma oddzielić nową treść od znanego rozwiązania pod inną nazwą.", `
    <form class="protocol-form" data-form="benchmark">
      <label>Stan bazowy<textarea name="baseline" required placeholder="Co przewiduje prostszy lub istniejący model?"></textarea></label>
      <label>Źródła<textarea name="sources" required placeholder="Jedno źródło lub identyfikator w wierszu"></textarea></label>
      <label>Wyszukiwanie istniejącego rozwiązania<textarea name="existing_solution_search" required></textarea></label>
      <label>Wynik porównania<textarea name="result" required></textarea></label>
      <button class="primary-button" type="submit">Zapisz benchmark</button>
    </form>`);
}

function reviewStep(benchmark) {
  return workflowShell("DARKROOM", "Wykonaj obowiązkową próbę obalenia", "Recenzent dostaje artefakt i dokładnie ten benchmark. Nie dostaje uzasadnienia autora ani pożądanego wyniku.", `
    <form class="protocol-form" data-form="review" data-benchmark="${escapeHTML(benchmark.benchmark_id)}">
      <label>Najsilniejszy zarzut<textarea name="strongest_objection" required></textarea></label>
      <label>Kontrprzykład<textarea name="counterexample" required></textarea></label>
      <label>Ukryte założenia<textarea name="hidden_assumptions" required placeholder="Jedno założenie w wierszu"></textarea></label>
      <label>Weryfikacja istniejącego rozwiązania<textarea name="existing_solution_search" required></textarea></label>
      <label>Test falsyfikacyjny<textarea name="falsification_test" required></textarea></label>
      <label>Minimalny wymagany dowód<textarea name="minimum_evidence_required" required></textarea></label>
      <div class="form-grid">
        <label>Rekomendacja<select name="recommendation"><option>TEST</option><option>REVISE</option><option>REJECT</option></select></label>
        <label>Pewność<input name="confidence" type="number" min="0" max="1" step="0.01" value="0.70" required></label>
      </div>
      <button class="primary-button" type="submit">Zapisz hostile review</button>
    </form>`);
}

function deflationStep(artifact, review) {
  return workflowShell("DEFLACJA", "Usuń to, czego nie da się utrzymać", `DARKROOM zalecił REVISE z pewnością ${review.confidence}. Zmień co najmniej jedno pole albo jawnie wycofaj twierdzenie.`, `
    <div class="notice">${escapeHTML(review.strongest_objection)}</div>
    <form class="protocol-form" data-form="deflation">
      <label>Kandydat po zawężeniu<textarea name="claim" required>${escapeHTML(artifact.claim)}</textarea></label>
      <label>Zakres po zawężeniu<textarea name="scope" required>${escapeHTML(artifact.scope)}</textarea></label>
      <label>Warunek falsyfikacji<textarea name="falsification_condition" required>${escapeHTML(artifact.falsification_condition)}</textarea></label>
      <label>Następny test<textarea name="next_test" required>${escapeHTML(artifact.next_test)}</textarea></label>
      <label>Wycofane twierdzenia<textarea name="withdrawn_claims" placeholder="Jedno w wierszu"></textarea></label>
      <label>Uzasadnienie deflacji<textarea name="rationale" required></textarea></label>
      <button class="primary-button" type="submit">Zapisz nową wersję</button>
    </form>`);
}

function decisionStep(review) {
  return workflowShell("DECYZJA CZŁOWIEKA", "Wybierz dalszy los hipotezy", `DARKROOM rekomenduje ${review.recommendation} z pewnością ${review.confidence}. Rekomendacja nie podejmuje decyzji za operatora.`, `
    <div class="notice">${escapeHTML(review.strongest_objection)}</div>
    <form class="protocol-form" data-form="decision">
      <label>Decyzja<select name="decision" id="decision-kind"><option>TEST</option><option>WAIT</option><option>REJECT</option><option>PUBLISH</option></select></label>
      <label>Uzasadnienie<textarea name="rationale" required></textarea></label>
      <div class="form-grid">
        <label>Operator<input name="operator_id" required placeholder="Twoje imię lub identyfikator"></label>
        <label>Powód odrzucenia<select name="reason_code"><option value="">Nie dotyczy</option>${["FALSIFIED", "CONTRADICTED", "REDUNDANT", "UNTESTABLE", "OUT_OF_SCOPE", "RESOURCE_LIMIT", "SUPERSEDED"].map((item) => `<option>${item}</option>`).join("")}</select></label>
      </div>
      <div class="form-grid">
        <label>Warunek powrotu<input name="reentry_condition" placeholder="Wymagany dla WAIT"></label>
        <label>Data przeglądu<input name="review_date" type="date"></label>
      </div>
      <label>Cel publikacji<input name="publication_target" placeholder="Wymagany dla PUBLISH"></label>
      <label class="checkbox-row"><input name="confirmed_by_human" type="checkbox" required><span>Potwierdzam, że tę decyzję podejmuję jako człowiek i rozumiem, że zakończy bieżący przebieg.</span></label>
      <button class="primary-button" type="submit">Zapisz DecisionMemo</button>
    </form>`);
}

function resumeForm() {
  return `<form class="protocol-form" data-form="resume">
    <label>Nowa podstawa dowodowa<textarea name="new_basis" required></textarea></label>
    <label>Tytuł nowego przebiegu<input name="title" placeholder="Opcjonalnie"></label>
    <button class="primary-button" type="submit">Utwórz powiązany przebieg</button>
  </form>`;
}

function resumeStep(state) {
  const memo = store.current.decision_memos.at(-1);
  const message = state === "waiting" ? `Powrót wymaga: ${memo.reentry_condition || "nowej podstawy"}.` : `Powód zakończenia: ${memo.reason_code || "REJECT"}.`;
  return workflowShell(state === "waiting" ? "POCZEKALNIA" : "CMENTARZ", "Historia pozostaje zamknięta", `${message} Wznowienie tworzy nowy zapis i zachowuje rodzica bez edycji.`, resumeForm());
}

function renderArtifact() {
  const artifact = currentArtifact(store.current);
  const fields = [
    ["Wyjaśniający kandydat", artifact.claim, true],
    ["Zakres", artifact.scope, true],
    ["Założenia", listText(artifact.assumptions), false],
    ["Dowody za", listText(artifact.evidence_for), false],
    ["Dowody przeciw", listText(artifact.evidence_against), false],
    ["Warunek falsyfikacji", artifact.falsification_condition, true],
    ["Następny test", artifact.next_test, true],
    ["Koszt eksploracji", artifact.exploration_cost, false],
  ];
  $("#panel-artifact").innerHTML = `<section class="data-section"><div class="section-heading"><div><span class="eyebrow">WERSJA ${store.current.versions.at(-1).number}</span><h3>Aktualny artefakt</h3><p>Poprzednie wersje pozostają w historii.</p></div></div>
    <div class="artifact-grid">${fields.map(([label, value, wide]) => `<div class="data-field ${wide ? "wide" : ""}"><span class="data-label">${label}</span><div class="data-value">${textOrDash(value)}</div></div>`).join("")}</div></section>`;
}

function renderEvidence() {
  const record = store.current;
  const items = [];
  record.benchmark_results.forEach((item) => items.push({
    kind: "Benchmark",
    title: item.baseline,
    meta: `v${item.artifact_version} · ${item.sources.join(", ")}`,
    body: `${item.existing_solution_search}\n${item.result}`,
  }));
  record.hostile_reviews.forEach((item) => items.push({
    kind: "DARKROOM",
    title: item.strongest_objection,
    meta: `${item.recommendation} · pewność ${item.confidence} · v${item.artifact_version}`,
    body: `Kontrprzykład: ${item.counterexample}\nMinimalny dowód: ${item.minimum_evidence_required}`,
    recommendation: item.recommendation,
  }));
  record.deflations.forEach((item) => items.push({
    kind: "Deflacja",
    title: item.rationale,
    meta: `v${item.from_version} → v${item.to_version}`,
    body: `Zmienione pola: ${item.changed_fields.join(", ") || "brak"}\nWycofane: ${item.withdrawn_claims.join(", ") || "brak"}`,
  }));
  record.decision_memos.forEach((item) => items.push({
    kind: "DecisionMemo",
    title: `${item.decision}: ${item.rationale}`,
    meta: `${item.approval.operator_id} · ${item.approval.channel}`,
    body: item.reason_code ? `Powód: ${item.reason_code}` : `Rekomendacja recenzenta: ${item.recommendation_seen}`,
    recommendation: item.decision,
  }));
  $("#panel-evidence").innerHTML = `<section class="data-section"><div class="section-heading"><div><span class="eyebrow">ŁAŃCUCH DOWODOWY</span><h3>Benchmark, recenzja i decyzja</h3><p>${items.length} zapisanych elementów.</p></div></div>
    ${items.length ? items.map((item) => `<article class="evidence-item"><div class="evidence-kind">${item.kind}</div><div class="evidence-body">${item.recommendation ? `<span class="recommendation">${escapeHTML(item.recommendation)}</span>` : ""}<h4>${escapeHTML(item.title)}</h4><p>${escapeHTML(item.meta)}</p><p>${escapeHTML(item.body).replaceAll("\n", "<br>")}</p></div></article>`).join("") : '<div class="notice">Łańcuch dowodowy jest jeszcze pusty.</div>'}</section>`;
}

function renderHistory() {
  const events = [...store.current.events].reverse();
  $("#panel-history").innerHTML = `<section class="data-section"><div class="section-heading"><div><span class="eyebrow">AUDYT</span><h3>Niezmienna historia zdarzeń</h3><p>${events.length} zdarzeń, rewizja ${store.current.revision}.</p></div></div>
    <ol class="timeline">${events.map((event) => `<li><time class="event-time">${formatDateTime(event.created_at)}</time><span class="event-line"></span><div><p class="event-name">${eventLabels[event.kind] || escapeHTML(event.kind)}</p><p class="event-payload">${escapeHTML(JSON.stringify(event.payload))}</p></div></li>`).join("")}</ol></section>`;
}

function formatDateTime(value) {
  try {
    return new Intl.DateTimeFormat("pl-PL", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
  } catch (_) {
    return value;
  }
}

async function mutate(path, payload, successMessage) {
  try {
    const response = await request(path, { method: "POST", body: JSON.stringify(payload) });
    toast(successMessage);
    await loadRecords();
    return response;
  } catch (error) {
    toast(error.message, "error");
    throw error;
  }
}

async function submitProtocol(form) {
  const record = store.current;
  const data = Object.fromEntries(new FormData(form));
  const kind = form.dataset.form;
  if (kind === "working") {
    await mutate(`/hypotheses/${record.id}/advance`, {
      state: "working",
      artifact: { ...data, assumptions: lines(data.assumptions), evidence_for: lines(data.evidence_for), evidence_against: lines(data.evidence_against) },
    }, "Utworzono hipotezę roboczą");
  } else if (kind === "benchmark") {
    await mutate(`/hypotheses/${record.id}/benchmark`, { ...data, sources: lines(data.sources) }, "Benchmark zapisany");
  } else if (kind === "review") {
    await mutate(`/hypotheses/${record.id}/review`, {
      ...data,
      benchmark_id: form.dataset.benchmark,
      hidden_assumptions: lines(data.hidden_assumptions),
      confidence: Number(data.confidence),
    }, "DARKROOM review zapisany");
  } else if (kind === "deflation") {
    const changes = {};
    for (const field of ["claim", "scope", "falsification_condition", "next_test"]) {
      if (data[field].trim() !== currentArtifact(record)[field]) changes[field] = data[field].trim();
    }
    await mutate(`/hypotheses/${record.id}/deflate`, {
      changes,
      withdrawn_claims: lines(data.withdrawn_claims),
      rationale: data.rationale,
    }, "Deflacja utworzyła nową wersję");
  } else if (kind === "decision") {
    await mutate(`/hypotheses/${record.id}/decision`, {
      ...data,
      confirmed_by_human: form.elements.confirmed_by_human.checked,
      channel: "praxis-gui",
    }, "DecisionMemo zapisane");
  } else if (kind === "resume") {
    const response = await mutate(`/hypotheses/${record.id}/resume`, data, "Utworzono powiązany przebieg");
    const nextId = response.hypothesis.id;
    await selectRecord(nextId);
  }
}

document.addEventListener("click", async (event) => {
  const dialogClose = event.target.closest("[data-dialog-close]");
  if (dialogClose) {
    dialogClose.closest("dialog")?.close();
    return;
  }
  const row = event.target.closest(".hypothesis-row");
  if (row) return selectRecord(row.dataset.id);
  const tab = event.target.closest("[data-tab]");
  if (tab) {
    store.tab = tab.dataset.tab;
    return renderTabs();
  }
  const advance = event.target.closest("[data-advance]");
  if (advance) return mutate(`/hypotheses/${store.current.id}/advance`, { state: advance.dataset.advance }, `Etap: ${stateLabels[advance.dataset.advance]}`);
  const tabJump = event.target.closest("[data-tab-jump]");
  if (tabJump) {
    store.tab = tabJump.dataset.tabJump;
    return renderTabs();
  }
  const actionButton = event.target.closest("[data-action]");
  const action = actionButton?.dataset.action;
  if (action === "new") {
    $("#new-title").value = "";
    $("#new-title").setCustomValidity("");
    $("#new-dialog").showModal();
    $("#new-title").focus();
  } else if (action === "refresh") {
    const loaded = await withBusyButton(actionButton, () => loadRecords());
    if (loaded) toast("Rejestr odświeżony");
  } else if (action === "refresh-record" && store.current) {
    const loaded = await withBusyButton(actionButton, () => selectRecord(store.current.id));
    if (loaded) toast("Zapis odświeżony");
  } else if (action === "home") {
    store.current = null;
    renderList();
    renderWorkspace();
  } else if (action === "preflight") {
    mutate(`/hypotheses/${store.current.id}/preflight`, {}, "Preflight zakończony");
  }
});

document.addEventListener("submit", async (event) => {
  if (event.target.id === "new-form") {
    event.preventDefault();
    const titleInput = $("#new-title");
    const title = titleInput.value.trim();
    if (!title) {
      titleInput.setCustomValidity("Wpisz tytuł lub obserwację.");
      titleInput.reportValidity();
      toast("Wpisz tytuł lub obserwację.", "error");
      return;
    }
    const button = event.target.querySelector("button[type=submit]");
    try {
      const payload = await withBusyButton(button, () => request("/hypotheses", { method: "POST", body: JSON.stringify({ title }) }));
      $("#new-dialog").close();
      toast("Seed utworzony");
      await loadRecords({ keepSelection: false });
      await selectRecord(payload.hypothesis.id);
    } catch (error) {
      toast(error.message, "error");
    }
    return;
  }
  const form = event.target.closest(".protocol-form");
  if (form) {
    event.preventDefault();
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      await submitProtocol(form);
    } catch (_) {
      button.disabled = false;
    }
  }
});

$("#search").addEventListener("input", (event) => {
  store.query = event.target.value;
  renderList();
});

$("#new-title").addEventListener("input", (event) => {
  event.target.setCustomValidity("");
});

window.addEventListener("unhandledrejection", (event) => {
  event.preventDefault();
  toast(event.reason?.message || "Akcja nie mogła zostać wykonana.", "error");
});

$("#today").textContent = new Intl.DateTimeFormat("pl-PL", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
loadRecords({ keepSelection: false });
