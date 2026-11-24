import io
from pathlib import Path

import pandas as pd
import streamlit as st

import engine
from i18n import OPTIONS, TEXT, option_label

st.set_page_config(page_title="NidhiFinder", page_icon="🇮🇳", layout="centered")

SAMPLE_PATH = Path(__file__).parent / "schemes.csv"

# ---------------------------------------------------------------- language
lang_choice = st.sidebar.radio(
    TEXT["en"]["language"], ["English", "हिन्दी"], horizontal=True, key="lang_choice"
)
lang = "hi" if lang_choice == "हिन्दी" else "en"
T = TEXT[lang]

st.title(T["title"])
st.caption(T["subtitle"])


# ---------------------------------------------------------------- dataset
@st.cache_data(show_spinner=False)
def load_dataset(data: bytes, filename: str) -> pd.DataFrame:
    """Read + clean a dataset with pandas (cached until the file changes)."""
    raw = engine.read_dataset(io.BytesIO(data), filename)
    return engine.normalize_dataset(raw)


st.sidebar.header(T["dataset_header"])
uploaded = st.sidebar.file_uploader(
    T["upload"], type=["csv", "xlsx", "xls"], help=T["upload_help"]
)
st.sidebar.download_button(
    T["template_dl"], SAMPLE_PATH.read_bytes(), "schemes_template.csv", mime="text/csv"
)

df, source_name = None, SAMPLE_PATH.name
if uploaded is not None:
    try:
        df = load_dataset(uploaded.getvalue(), uploaded.name)
        source_name = uploaded.name
    except Exception as err:  # bad columns, wrong format, missing openpyxl, ...
        st.sidebar.error(T["dataset_error"].format(err=err))
if df is None:
    df = load_dataset(SAMPLE_PATH.read_bytes(), SAMPLE_PATH.name)

st.sidebar.success(T["dataset_loaded"].format(src=source_name, n=len(df)))

with st.expander(T["preview"]):
    st.dataframe(engine.to_display(df), hide_index=True)


# ---------------------------------------------------------------- form
def options(kind: str, column: str) -> list[str]:
    """Built-in options plus any extra values found in the dataset."""
    base = list(OPTIONS[kind])
    return base + [v for v in engine.collect_values(df, column) if v not in base]


def yes_no(label: str, key: str) -> bool:
    return st.radio(
        label,
        [False, True],
        format_func=lambda b: T["yes"] if b else T["no"],
        horizontal=True,
        key=key,
    )


st.subheader(T["form_header"])
with st.form("eligibility_form"):
    c1, c2 = st.columns(2)
    with c1:
        age = st.number_input(T["lbl_age"], min_value=1, max_value=100, value=22, key="age")
        gender = st.selectbox(
            T["lbl_gender"], options("gender", "genders"),
            format_func=lambda v: option_label("gender", v, lang), key="gender",
        )
        occupation = st.selectbox(
            T["lbl_occupation"], options("occupation", "occupations"),
            format_func=lambda v: option_label("occupation", v, lang), key="occupation",
        )
        area = st.selectbox(
            T["lbl_area"], options("area", "areas"),
            format_func=lambda v: option_label("area", v, lang), key="area",
        )
    with c2:
        income = st.number_input(
            T["lbl_income"], min_value=0, value=150000, step=10000, key="income"
        )
        state = st.selectbox(
            T["lbl_state"], options("state", "states"),
            format_func=lambda v: option_label("state", v, lang), key="state",
        )
        category = st.selectbox(
            T["lbl_category"], options("category", "categories"),
            format_func=lambda v: option_label("category", v, lang), key="category",
        )
        education = st.selectbox(
            T["lbl_education"], options("education", "education"),
            format_func=lambda v: option_label("education", v, lang), key="education",
        )

    disability = yes_no(T["lbl_disability"], "disability")
    bpl = yes_no(T["lbl_bpl"], "bpl")
    land = yes_no(T["lbl_land"], "land")
    minority = yes_no(T["lbl_minority"], "minority")

    submitted = st.form_submit_button(T["submit"])


# ---------------------------------------------------------------- results
def scheme_text(scheme: dict, field: str) -> str:
    return scheme[f"{field}_{lang}"]


def format_reason(code: str, params: dict) -> str:
    if code == "age":
        return T["reason_age"].format(**params)
    if code == "income":
        return T["reason_income"].format(max=engine.format_inr(params["max"]))
    if code == "list":
        field = params["field"]
        values = ", ".join(option_label(field, v, lang) for v in params["allowed"])
        return T["reason_list"].format(field=T[f"lbl_{field}"], values=values)
    return T[f"reason_{code}"]  # flag_disability, flag_bpl, ...


if submitted:
    profile = {
        "age": age, "income": income, "gender": gender, "state": state,
        "area": area, "occupation": occupation, "category": category,
        "education": education, "disability": disability, "bpl": bpl,
        "land": land, "minority": minority,
    }
    eligible, rejected = engine.evaluate(df, profile)

    if eligible:
        st.success(T["success"].format(n=len(eligible)))
        for scheme, _ in eligible:
            st.subheader(scheme_text(scheme, "name"))
            st.write(scheme_text(scheme, "benefit"))
            st.link_button(T["apply"], scheme["url"])

        results = pd.DataFrame(
            {
                T["col_scheme"]: [scheme_text(s, "name") for s, _ in eligible],
                T["col_portal"]: [s["url"] for s, _ in eligible],
            }
        )
        st.dataframe(
            results,
            hide_index=True,
            column_config={T["col_portal"]: st.column_config.LinkColumn(T["col_portal"])},
        )
        # utf-8-sig so Hindi opens correctly in Excel
        st.download_button(
            T["download"],
            results.to_csv(index=False).encode("utf-8-sig"),
            "eligible_schemes.csv",
            mime="text/csv",
        )
    else:
        st.warning(T["none"])

    if rejected:
        with st.expander(T["rejected_header"]):
            for scheme, reasons in rejected:
                st.markdown(f"**{scheme_text(scheme, 'name')}**")
                for code, params in reasons:
                    st.markdown(f"- {format_reason(code, params)}")

st.divider()
st.caption(T["disclaimer"])
