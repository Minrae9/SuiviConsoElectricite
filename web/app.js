/**
 * app.js — Dashboard compact Mint-Energie
 */

const DATA_CANDIDATE_PATHS = [
    "../data/conso_processed.json",
    "./data/conso_processed.json",
    "/data/conso_processed.json",
];
let appData = null;

const MONTH_NAMES = [
    "Jan", "Fev", "Mar", "Avr", "Mai", "Juin",
    "Juil", "Aout", "Sep", "Oct", "Nov", "Dec",
];

// Palette par annee
const YEAR_COLORS = [
    { bar: "rgba(79, 195, 247, 0.7)", line: "#4fc3f7" },   // 2024 - bleu
    { bar: "rgba(102, 187, 106, 0.7)", line: "#66bb6a" },   // 2025 - vert
    { bar: "rgba(255, 167, 38, 0.7)", line: "#ffa726" },    // 2026 - orange
    { bar: "rgba(171, 71, 188, 0.7)", line: "#ab47bc" },    // 2027 - violet
];

// ============================================================
// Chargement
// ============================================================

async function loadData() {
    try {
        const response = await fetchDataFromKnownPaths();
        appData = await response.json();

        renderKPIs();
        renderMonthlyTable();
        renderConsoMonths();
        renderPrixMonths();
        renderPctMonths();
        renderYearly();
        renderLastUpdate();
    } catch (e) {
        document.getElementById("error-message").textContent = e.message;
        document.getElementById("error-banner").classList.remove("hidden");
    }
}

async function fetchDataFromKnownPaths() {
    const errors = [];

    for (const path of DATA_CANDIDATE_PATHS) {
        const url = new URL(path, window.location.href).toString();
        try {
            const resp = await fetch(url);
            if (resp.ok) return resp;
            errors.push(`${path} (HTTP ${resp.status})`);
        } catch (err) {
            errors.push(`${path} (${err.message})`);
        }
    }

    throw new Error(`Impossible de charger les donnees JSON: ${errors.join(" | ")}`);
}

// ============================================================
// Helpers
// ============================================================

function buildYearMonthMap(field) {
    const map = {};
    const years = new Set();
    appData.monthly.forEach(m => {
        const [y, mo] = m.billing_month.split("-");
        years.add(y);
        if (!map[y]) map[y] = {};
        map[y][mo] = m[field] || 0;
    });
    return { map, years: Array.from(years).sort() };
}

function fmt(n) {
    if (n == null || isNaN(n)) return "—";
    return n.toLocaleString("fr-FR", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function fmt1(n) {
    if (n == null || isNaN(n)) return "—";
    return n.toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function fmt2(n) {
    if (n == null || isNaN(n)) return "—";
    return n.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function computeVariationPct(current, previous) {
    if (current == null || previous == null || previous === 0) return null;
    return +(((current - previous) / previous) * 100).toFixed(1);
}

function formatVariationLabel(value) {
    if (value == null || isNaN(value)) return "—";
    const abs = Math.abs(value).toLocaleString("fr-FR", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
    });
    if (value < 0) return `${abs}% en moins`;
    if (value > 0) return `+${abs}% en plus`;
    return "0,0%";
}

function chartDefaults() {
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 600 },
        interaction: { intersect: false, mode: "index" },
        plugins: {
            legend: {
                position: "top",
                labels: { color: "#8899aa", font: { size: 11 }, padding: 8, boxWidth: 14 },
            },
            tooltip: {
                backgroundColor: "rgba(15, 25, 35, 0.95)",
                titleColor: "#e8edf2",
                bodyColor: "#ccd6e0",
                cornerRadius: 6,
                padding: 8,
                bodyFont: { size: 12 },
            },
        },
        scales: {
            x: {
                grid: { color: "rgba(45, 64, 80, 0.5)", lineWidth: 0.5 },
                ticks: { color: "#8899aa", font: { size: 10 } },
            },
            y: {
                grid: { color: "rgba(45, 64, 80, 0.5)", lineWidth: 0.5 },
                ticks: { color: "#8899aa", font: { size: 10 } },
                beginAtZero: true,
            },
        },
    };
}

// ============================================================
// KPIs
// ============================================================

function renderKPIs() {
    const s = appData.summary;
    document.getElementById("kpi-total").textContent = fmt(s.total_kwh);
    document.getElementById("kpi-hp-hc").innerHTML =
        `<span style="color:#ef5350">${fmt(s.hp_kwh)}</span> / <span style="color:#26c6da">${fmt(s.hc_kwh)}</span>`;
    document.getElementById("kpi-hp-hc-pct").textContent =
        `HP ${s.hp_ratio}% | HC ${s.hc_ratio}%`;
    document.getElementById("kpi-factures").textContent =
        s.total_factures_euros ? fmt2(s.total_factures_euros) : "—";
    document.getElementById("kpi-prix").textContent =
        s.avg_prix_kwh ? fmt2(s.avg_prix_kwh * 100) : "—";
    document.getElementById("kpi-avg").textContent = fmt(s.avg_monthly_kwh);
    document.getElementById("kpi-nb-months").textContent = `${s.nb_months} mois`;

    if (s.date_debut && s.date_fin) {
        const fmtD = d => d.split("-").reverse().join("/");
        document.getElementById("kpi-period").textContent =
            `${fmtD(s.date_debut)} — ${fmtD(s.date_fin)}`;
    }
}

function renderMonthlyTable() {
    const body = document.getElementById("monthly-data-body");
    if (!body) return;

    const rows = [...(appData.monthly || [])].sort((a, b) => {
        if (a.billing_month < b.billing_month) return 1;
        if (a.billing_month > b.billing_month) return -1;
        return 0;
    });

    body.innerHTML = rows.map(m => {
        const amount = m.montant_euros == null ? "—" : fmt2(m.montant_euros);
        const unitPrice = m.prix_kwh == null ? "—" : m.prix_kwh.toLocaleString("fr-FR", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
        return `
            <tr>
                <td>${m.label || m.billing_month || "—"}</td>
                <td>${m.period_label || "—"}</td>
                <td>${fmt(m.total_kwh)}</td>
                <td>${fmt(m.hp_kwh)}</td>
                <td>${fmt(m.hc_kwh)}</td>
                <td>${fmt1(m.hp_ratio)}</td>
                <td>${fmt1(m.hc_ratio)}</td>
                <td>${amount}</td>
                <td>${unitPrice}</td>
            </tr>
        `;
    }).join("");
}

// ============================================================
// 1. Comparaison conso mensuelle par annee
// ============================================================

function renderConsoMonths() {
    const { map, years } = buildYearMonthMap("total_kwh");
    const months = ["01","02","03","04","05","06","07","08","09","10","11","12"];

    const datasets = years.map((y, i) => ({
        label: y,
        data: months.map(m => map[y]?.[m] || 0),
        backgroundColor: YEAR_COLORS[i % YEAR_COLORS.length].bar,
        borderColor: YEAR_COLORS[i % YEAR_COLORS.length].line,
        borderWidth: 1,
        borderRadius: 3,
    }));

    const opts = chartDefaults();
    opts.scales.y.ticks.callback = v => `${v}`;
    opts.plugins.tooltip.callbacks = {
        label: ctx => ` ${ctx.dataset.label}: ${fmt(ctx.parsed.y)} kWh`,
    };

    new Chart(document.getElementById("chart-conso-months"), {
        type: "bar",
        data: { labels: MONTH_NAMES, datasets },
        options: opts,
    });
}

// ============================================================
// 2. Comparaison prix mensuel par annee
// ============================================================

function renderPrixMonths() {
    const { map, years } = buildYearMonthMap("montant_euros");
    const months = ["01","02","03","04","05","06","07","08","09","10","11","12"];

    const datasets = years.map((y, i) => ({
        label: y,
        data: months.map(m => map[y]?.[m] || 0),
        backgroundColor: YEAR_COLORS[i % YEAR_COLORS.length].bar,
        borderColor: YEAR_COLORS[i % YEAR_COLORS.length].line,
        borderWidth: 1,
        borderRadius: 3,
    }));

    const opts = chartDefaults();
    opts.scales.y.ticks.callback = v => `${v} €`;
    opts.plugins.tooltip.callbacks = {
        label: ctx => ` ${ctx.dataset.label}: ${fmt2(ctx.parsed.y)} €`,
    };

    new Chart(document.getElementById("chart-prix-months"), {
        type: "bar",
        data: { labels: MONTH_NAMES, datasets },
        options: opts,
    });
}

// ============================================================
// 3. Variation mensuelle vs annee precedente (%)
// ============================================================

function renderPctMonths() {
    const consoData = buildYearMonthMap("total_kwh");
    const prixData = buildYearMonthMap("montant_euros");
    const years = consoData.years;
    const months = ["01","02","03","04","05","06","07","08","09","10","11","12"];

    if (years.length < 2) return;

    const datasets = [];
    years.forEach((year, i) => {
        if (i === 0) return;
        const prevYear = years[i - 1];
        const color = YEAR_COLORS[i % YEAR_COLORS.length].line;

        datasets.push({
            label: `${year} conso vs ${prevYear}`,
            data: months.map(m => {
                const current = consoData.map[year]?.[m];
                const previous = consoData.map[prevYear]?.[m];
                return computeVariationPct(current, previous);
            }),
            borderColor: color,
            backgroundColor: "transparent",
            borderWidth: 2.5,
            pointRadius: 3,
            pointBackgroundColor: color,
            pointHoverRadius: 5,
            tension: 0.25,
            spanGaps: true,
        });

        datasets.push({
            label: `${year} prix vs ${prevYear}`,
            data: months.map(m => {
                const current = prixData.map[year]?.[m];
                const previous = prixData.map[prevYear]?.[m];
                return computeVariationPct(current, previous);
            }),
            borderColor: color,
            backgroundColor: "transparent",
            borderDash: [6, 4],
            borderWidth: 2,
            pointRadius: 2.5,
            pointBackgroundColor: color,
            pointStyle: "rectRot",
            pointHoverRadius: 4,
            tension: 0.25,
            spanGaps: true,
        });
    });

    const opts = chartDefaults();
    opts.scales.y.ticks.callback = v => `${v}%`;
    opts.scales.y.grid = {
        color: ctx => (ctx.tick.value === 0 ? "rgba(136, 153, 170, 0.7)" : "rgba(45, 64, 80, 0.5)"),
        lineWidth: ctx => (ctx.tick.value === 0 ? 1.2 : 0.5),
    };
    opts.plugins.tooltip.callbacks = {
        label: ctx => ` ${ctx.dataset.label}: ${formatVariationLabel(ctx.parsed.y)}`,
    };

    new Chart(document.getElementById("chart-pct-months"), {
        type: "line",
        data: { labels: MONTH_NAMES, datasets },
        options: opts,
    });
}

// ============================================================
// 4. Variation annuelle vs annee precedente (%)
// ============================================================

function renderYearly() {
    const comparison = appData.summary.yearly_comparison;
    if (!comparison || comparison.length < 2) return;

    // Calculer total factures par annee
    const yearInvoices = {};
    const yearMonthCount = {};
    appData.monthly.forEach(m => {
        const y = m.billing_month.split("-")[0];
        if (!yearInvoices[y]) yearInvoices[y] = 0;
        if (!yearMonthCount[y]) yearMonthCount[y] = 0;
        yearMonthCount[y] += 1;
        if (m.montant_euros) yearInvoices[y] += m.montant_euros;
    });

    const labels = [];
    const consoYoY = [];
    const prixYoY = [];

    for (let i = 1; i < comparison.length; i += 1) {
        const current = comparison[i];
        const previous = comparison[i - 1];

        // Ne pas afficher de pourcentage si une des deux annees est incomplete.
        const isCurrentFullYear = (yearMonthCount[current.year] || 0) === 12;
        const isPreviousFullYear = (yearMonthCount[previous.year] || 0) === 12;
        if (!isCurrentFullYear || !isPreviousFullYear) {
            continue;
        }

        labels.push(current.year);
        consoYoY.push(computeVariationPct(current.total_kwh, previous.total_kwh));
        prixYoY.push(computeVariationPct(yearInvoices[current.year], yearInvoices[previous.year]));
    }

    if (labels.length === 0) return;

    const opts = chartDefaults();
    opts.scales.y = {
        grid: {
            color: ctx => (ctx.tick.value === 0 ? "rgba(136, 153, 170, 0.7)" : "rgba(45, 64, 80, 0.5)"),
            lineWidth: ctx => (ctx.tick.value === 0 ? 1.2 : 0.5),
        },
        ticks: { color: "#4fc3f7", font: { size: 10 }, callback: v => `${v}%` },
        beginAtZero: true,
    };
    opts.plugins.tooltip.callbacks = {
        label: function (ctx) {
            if (ctx.dataset.type === "line") {
                return ` Prix: ${formatVariationLabel(ctx.parsed.y)}`;
            }
            return ` Conso: ${formatVariationLabel(ctx.parsed.y)}`;
        },
    };

    new Chart(document.getElementById("chart-yearly"), {
        type: "bar",
        data: {
            labels,
            datasets: [
                {
                    label: "Conso vs N-1",
                    data: consoYoY,
                    backgroundColor: consoYoY.map(v => (v == null || v >= 0 ? "rgba(102, 187, 106, 0.65)" : "rgba(239, 83, 80, 0.65)")),
                    borderColor: consoYoY.map(v => (v == null || v >= 0 ? "#66bb6a" : "#ef5350")),
                    borderWidth: 1,
                    borderRadius: 3,
                    yAxisID: "y",
                },
                {
                    label: "Prix vs N-1",
                    data: prixYoY,
                    type: "line",
                    borderColor: "#ffa726",
                    backgroundColor: "rgba(255, 167, 38, 0.15)",
                    borderWidth: 3,
                    pointRadius: 5,
                    pointBackgroundColor: "#ffa726",
                    pointHoverRadius: 7,
                    fill: true,
                    tension: 0.2,
                    yAxisID: "y",
                    spanGaps: true,
                },
            ],
        },
        options: opts,
    });
}

// ============================================================
// Last update
// ============================================================

function renderLastUpdate() {
    if (appData.generated_at) {
        document.getElementById("last-update").textContent =
            `MAJ : ${appData.generated_at}`;
    }
}

// ============================================================
// Init
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
    try { Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif"; } catch(e) {}
    loadData();
});
