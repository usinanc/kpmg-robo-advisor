import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import plotly.express as px
import streamlit as st


BASE_DIR = Path(__file__).resolve().parent

FILES = {
    "market": BASE_DIR / "makro_gostergeler.csv",
    "summary": BASE_DIR / "genel_ozet.csv",
    "profiles": BASE_DIR / "yatirimci_profilleri.csv",
    "portfolio": BASE_DIR / "portfoy_onerileri.csv",
    "funds": BASE_DIR / "fon_gostergeleri.csv",
}

UI_PROFILE_LABELS = {
    "Defansif": "Defansif",
    "Temkinli": "Temkinli",
    "Dengeli": "Dengeli",
    "Büyüme": "Büyüme Odaklı",
    "Spekülatif": "Spekülatif",
}

# From user-provided analysis-summary example.
PPTX_BENCHMARK_MULTIPLIERS_5Y = {"Büyüme Odaklı": 12.5}


def normalize_text(value: str) -> str:
    value = str(value or "").strip().lower()
    replacements = {
        "ý": "i",
        "þ": "s",
        "ð": "g",
        "Ý": "i",
        "Þ": "s",
        "Ð": "g",
        "ö": "o",
        "ü": "u",
        "ç": "c",
        "ı": "i",
        "Ö": "o",
        "Ü": "u",
        "Ç": "c",
        "İ": "i",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"\s+", " ", value)
    return value


def read_lines(path: Path) -> List[str]:
    for enc in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            text = path.read_text(encoding=enc)
            return [line.rstrip("\n\r") for line in text.splitlines()]
        except Exception:
            continue
    return []


def parse_percent(value: str) -> float:
    txt = str(value or "").replace("%", "").replace(",", ".").strip()
    if txt in ("", "-", "?", "??", "?"):
        return 0.0
    match = re.search(r"-?\d+(\.\d+)?", txt)
    return float(match.group(0)) if match else 0.0


def parse_market_indicators(lines: List[str]) -> pd.DataFrame:
    start_idx = -1
    for i, line in enumerate(lines):
        norm = normalize_text(line)
        if "donem" in norm and "enf" in norm and "faiz" in norm:
            start_idx = i
            break

    if start_idx == -1:
        return pd.DataFrame(columns=["Dönem", "Enflasyon", "Politika Faizi"])

    data = []
    for line in lines[start_idx + 1 :]:
        parts = [p.strip() for p in line.split(";")]
        if not parts or not parts[0]:
            if data:
                break
            continue
        if not re.match(r"^\d{4}-\d{2}$", parts[0]):
            continue
        enf = parse_percent(parts[1] if len(parts) > 1 else "")
        faiz = parse_percent(parts[2] if len(parts) > 2 else "")
        data.append({"Dönem": parts[0], "Enflasyon": enf, "Politika Faizi": faiz})

    df = pd.DataFrame(data)
    return df.tail(12)


def parse_basic_findings(lines: List[str]) -> List[Tuple[str, str]]:
    findings: List[Tuple[str, str]] = []
    for line in lines:
        parts = [p.strip() for p in line.split(";")]
        if not parts:
            continue
        if parts[0].isdigit() and len(parts) >= 4:
            title = parts[1]
            detail = parts[3]
            if title and detail:
                findings.append((title, detail))
    return findings


def parse_profile_notes(lines: List[str]) -> Dict[str, Dict[str, str]]:
    profile_names = ["Defansif", "Temkinli", "Dengeli", "Büyüme", "Spekülatif"]
    data = {p: {"Tanım": "", "Risk Seviyesi": "", "Yatırım Ufku": "", "Beklenen Getiri": ""} for p in profile_names}
    current = None
    for line in lines:
        parts = [p.strip() for p in line.split(";")]
        key = parts[0] if parts else ""
        if key in profile_names:
            current = key
            continue
        if not current or len(parts) < 2:
            continue
        if parts[0] in data[current]:
            data[current][parts[0]] = parts[1]
    return data


def parse_portfolio_weights(lines: List[str]) -> pd.DataFrame:
    header_idx = -1
    for i, line in enumerate(lines):
        if "Enstrüman" in line and "Defansif" in line and "Spekülatif" in line:
            header_idx = i
            break
    if header_idx == -1:
        return pd.DataFrame()

    rows = []
    for line in lines[header_idx + 1 :]:
        parts = [p.strip() for p in line.split(";")]
        if not parts or not parts[0]:
            if rows:
                break
            continue
        if "3 YILLIK" in parts[0]:
            break
        asset = parts[0]
        if asset.lower().startswith("profil"):
            continue
        row = {
            "Asset": asset,
            "Defansif": parse_percent(parts[1] if len(parts) > 1 else ""),
            "Temkinli": parse_percent(parts[2] if len(parts) > 2 else ""),
            "Dengeli": parse_percent(parts[3] if len(parts) > 3 else ""),
            "Büyüme": parse_percent(parts[4] if len(parts) > 4 else ""),
            "Spekülatif": parse_percent(parts[5] if len(parts) > 5 else ""),
            "Görüş": parts[6] if len(parts) > 6 else "",
        }
        rows.append(row)
    return pd.DataFrame(rows)


def parse_return_scenarios(lines: List[str]) -> pd.DataFrame:
    header_idx = -1
    for i, line in enumerate(lines):
        if "Profil;" in line and "Y. Getiri (Min)" in line:
            header_idx = i
            break
    if header_idx == -1:
        return pd.DataFrame()

    rows = []
    for line in lines[header_idx + 1 :]:
        parts = [p.strip() for p in line.split(";")]
        if not parts or not parts[0]:
            continue
        if parts[0] not in ["Defansif", "Temkinli", "Dengeli", "Büyüme", "Spekülatif"]:
            continue
        rows.append(
            {
                "Profil": parts[0],
                "MinAnnual": parse_percent(parts[1] if len(parts) > 1 else "") / 100.0,
                "MaxAnnual": parse_percent(parts[2] if len(parts) > 2 else "") / 100.0,
                "Recommendation": parts[6] if len(parts) > 6 else "",
            }
        )
    return pd.DataFrame(rows)


def parse_funds(lines: List[str]) -> pd.DataFrame:
    records = []
    for i, line in enumerate(lines):
        if "Kategori:" not in line:
            continue
        prev = lines[i - 1] if i > 0 else ""
        name_chunks = [x.strip() for x in re.split(r";{2,}", prev) if x.strip()]
        info_chunks = [x.strip() for x in re.split(r";{2,}", line) if "Kategori:" in x]
        for name, info in zip(name_chunks, info_chunks):
            cat_match = re.search(r"Kategori:\s*([^|]+)\|", info, flags=re.IGNORECASE)
            ret_match = re.search(r"Getiri:\s*%?\s*([0-9,\.]+)", info, flags=re.IGNORECASE)
            category = cat_match.group(1).strip() if cat_match else "Diğer"
            one_year = ret_match.group(1).replace(",", ".") if ret_match else ""
            records.append({"Fund": name, "Category": category, "1YReturnPct": one_year})
    return pd.DataFrame(records)


def suggest_profile_from_quiz(scores: List[int]) -> str:
    total = sum(scores)
    if total <= 8:
        return "Defansif"
    if total <= 12:
        return "Temkinli"
    if total <= 16:
        return "Dengeli"
    if total <= 20:
        return "Büyüme"
    return "Spekülatif"


def map_asset_to_fund_keywords(asset: str) -> List[str]:
    a = normalize_text(asset)
    if "tl mevduat" in a:
        return ["para piyasasi", "borclanma"]
    if "devlet tahvili" in a or "hazine bonosu" in a or "tufe" in a:
        return ["borclanma", "katilim"]
    if "usd mevduat" in a:
        return ["yabanci", "eurobond", "borclanma"]
    if "altin" in a:
        return ["altin"]
    if "bist" in a:
        return ["hisse"]
    if "eurobond" in a:
        return ["eurobond", "borclanma"]
    if "kripto" in a:
        return ["teknoloji", "yabanci"]
    return []


def filter_representative_funds(funds_df: pd.DataFrame, portfolio_assets: List[str]) -> pd.DataFrame:
    picks = []
    for asset in portfolio_assets:
        keys = map_asset_to_fund_keywords(asset)
        if not keys:
            continue
        subset = funds_df[
            funds_df["Category"].apply(lambda x: any(k in normalize_text(x) for k in keys))
        ].head(2)
        for _, row in subset.iterrows():
            picks.append({"Asset": asset, "Fund": row["Fund"], "Category": row["Category"], "1YReturnPct": row["1YReturnPct"]})
    return pd.DataFrame(picks)


@st.cache_data
def load_all_data():
    market_lines = read_lines(FILES["market"])
    summary_lines = read_lines(FILES["summary"])
    profile_lines = read_lines(FILES["profiles"])
    portfolio_lines = read_lines(FILES["portfolio"])
    fund_lines = read_lines(FILES["funds"])

    market_df = parse_market_indicators(market_lines)
    findings = parse_basic_findings(summary_lines)
    profile_notes = parse_profile_notes(profile_lines)
    weights_df = parse_portfolio_weights(portfolio_lines)
    returns_df = parse_return_scenarios(portfolio_lines)
    funds_df = parse_funds(fund_lines)

    return market_df, findings, profile_notes, weights_df, returns_df, funds_df


def main():
    st.set_page_config(page_title="KPMG IxT - Akıllı Yatırım Asistanı", layout="centered")
    st.title("KPMG IxT - Akıllı Yatırım Asistanı")
    st.caption("Veri kaynakları: makro_gostergeler.csv, genel_ozet.csv, yatirimci_profilleri.csv, portfoy_onerileri.csv, fon_gostergeleri.csv")

    market_df, findings, profile_notes, weights_df, returns_df, funds_df = load_all_data()

    if weights_df.empty:
        st.error("Portföy ağırlıkları okunamadı. Lütfen CSV formatını kontrol edin.")
        return

    if "asama" not in st.session_state:
        st.session_state.asama = 1
    if "final_amount" not in st.session_state:
        st.session_state.final_amount = 250000.0
    if "final_profile" not in st.session_state:
        st.session_state.final_profile = ""
    if "balon_goster" not in st.session_state:
        st.session_state.balon_goster = False

    top_container = st.container()
    with top_container:
        st.subheader("Kapak Göstergeleri")
        if not market_df.empty:
            latest = market_df.iloc[-1]
            prev = market_df.iloc[-2] if len(market_df) > 1 else latest
            c1, c2, c3 = st.columns(3)
            c1.metric("Dönem", str(latest["Dönem"]))
            c2.metric("Enflasyon", f"%{float(latest['Enflasyon']):.2f}", delta=f"{float(latest['Enflasyon']) - float(prev['Enflasyon']):+.2f} pp")
            c3.metric("Politika Faizi", f"%{float(latest['Politika Faizi']):.2f}", delta=f"{float(latest['Politika Faizi']) - float(prev['Politika Faizi']):+.2f} pp")
        else:
            st.info("Makro göstergeler okunamadı.")

    if st.session_state.asama == 1:
        st.subheader("Aşama 1: Giriş ve Yatırım Tutarı")
        with st.container(border=True):
            amount = st.number_input(
                "Yatırıma ayırmak istediğiniz toplam tutar nedir? (TL)",
                min_value=1000.0,
                value=float(st.session_state.final_amount),
                step=5000.0,
            )
            if st.button("Risk Anketine Geç", type="primary", use_container_width=True):
                st.session_state.final_amount = amount
                st.session_state.asama = 2
                st.rerun()

    elif st.session_state.asama == 2:
        st.subheader("Aşama 2: Risk Anketi")
        with st.container(border=True):
            q1 = st.radio("Soru 1: Yatırım vadeniz nedir?", ["Kısa", "Orta", "Uzun"], index=1)
            q2 = st.radio(
                "Soru 2: Ana paranızın değer kaybetme riskine ne kadar tahammülünüz var?",
                ["Hiç yok", "Az", "Orta", "Yüksek"],
                index=1,
            )
            q3 = st.radio(
                "Soru 3: Getiri beklentiniz nedir?",
                ["Enflasyon üzeri koruma", "Dengeli büyüme", "Maksimum kazanç"],
                index=1,
            )
            q4 = st.radio(
                "Soru 4: Piyasa dalgalandığında en olası yaklaşımınız nedir?",
                ["Pozisyonumu korurum", "Sınırlı değişiklik yaparım", "Fırsat gördükçe artırırım", "Agresif alım yaparım"],
                index=1,
            )
            score_map = {
                "Kısa": 1,
                "Orta": 3,
                "Uzun": 5,
                "Hiç yok": 1,
                "Az": 2,
                "Orta": 3,
                "Yüksek": 5,
                "Enflasyon üzeri koruma": 1,
                "Dengeli büyüme": 3,
                "Maksimum kazanç": 5,
                "Pozisyonumu korurum": 1,
                "Sınırlı değişiklik yaparım": 2,
                "Fırsat gördükçe artırırım": 4,
                "Agresif alım yaparım": 5,
            }

            if st.button("Hesapla", type="primary", use_container_width=True):
                selected_profile = suggest_profile_from_quiz(
                    [score_map[q1], score_map[q2], score_map[q3], score_map[q4]]
                )
                st.session_state.final_profile = selected_profile
                st.session_state.asama = 3
                st.session_state.balon_goster = True
                st.rerun()

    elif st.session_state.asama == 3:
        amount = float(st.session_state.final_amount)
        selected_profile = st.session_state.final_profile

        if st.session_state.balon_goster:
            st.balloons()
            st.session_state.balon_goster = False

        st.subheader("Aşama 3: Sonuç Ekranı")
        st.success(f"Atanan Yatırım Profili: {UI_PROFILE_LABELS[selected_profile]}")

        notes = profile_notes.get(selected_profile, {})
        with st.container(border=True):
            st.markdown("### Profil Tanımı")
            st.write(notes.get("Tanım", "-"))
            st.markdown(f"- **Risk Seviyesi:** {notes.get('Risk Seviyesi', '-')}")
            st.markdown(f"- **Yatırım Ufku:** {notes.get('Yatırım Ufku', '-')}")
            st.markdown(f"- **Beklenen Getiri:** {notes.get('Beklenen Getiri', '-')}")

        portfolio = weights_df[["Asset", selected_profile]].copy()
        portfolio = portfolio.rename(columns={selected_profile: "WeightPct"})
        portfolio = portfolio[portfolio["WeightPct"] > 0].copy()
        portfolio["AmountTL"] = (portfolio["WeightPct"] / 100.0) * amount
        portfolio = portfolio.sort_values("AmountTL", ascending=False)

        with st.container(border=True):
            st.markdown("### Portföy Dağılımı (TL)")
            show_df = portfolio.copy()
            show_df["WeightPct"] = show_df["WeightPct"].map(lambda x: f"%{x:.1f}")
            show_df["AmountTL"] = show_df["AmountTL"].map(lambda x: f"{x:,.0f} TL")
            st.dataframe(show_df, use_container_width=True, hide_index=True)

            fig = px.pie(portfolio, names="Asset", values="AmountTL", title="Portföy Dağılımı - Plotly Pie")
            fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig, use_container_width=True)

        with st.container(border=True):
            st.markdown("### Yatırım Gerekçesi / Temel Bulgular")
            for title, detail in findings[:6]:
                st.markdown(f"- **{title}:** {detail}")

        with st.container(border=True):
            st.markdown("### Historical Performance Simulation")
            years = st.slider("Simülasyon süresi (yıl)", min_value=1, max_value=5, value=5)
            scenario = returns_df[returns_df["Profil"] == selected_profile]
            if not scenario.empty:
                min_r = float(scenario["MinAnnual"].iloc[0])
                max_r = float(scenario["MaxAnnual"].iloc[0])
                future_min = amount * ((1 + min_r) ** years)
                future_max = amount * ((1 + max_r) ** years)
                st.markdown(
                    f"- **Veri kaynağı:** `portfoy_onerileri.csv` yıllık getiri bandı\n"
                    f"- **{years} yıllık olası aralık:** `{future_min:,.0f} TL` - `{future_max:,.0f} TL`\n"
                    f"- **Çarpan aralığı:** `x{future_min / amount:.2f}` - `x{future_max / amount:.2f}`"
                )
                rec = scenario["Recommendation"].iloc[0]
                if rec:
                    st.markdown(f"- **Profil önerisi notu:** {rec}")
            else:
                st.info("Getiri senaryosu bulunamadı.")

            selected_en = UI_PROFILE_LABELS[selected_profile]
            if selected_en in PPTX_BENCHMARK_MULTIPLIERS_5Y and years == 5:
                bench = PPTX_BENCHMARK_MULTIPLIERS_5Y[selected_en]
                st.markdown(f"**Analiz özeti benchmark:** {selected_en} profilinde 5 yılda yaklaşık `x{bench}` senaryo örneği.")

        if st.button("Yeniden Hesapla / Anketi Tekrarla", use_container_width=True):
            st.session_state.asama = 1
            st.session_state.final_profile = ""
            st.rerun()


if __name__ == "__main__":
    main()
