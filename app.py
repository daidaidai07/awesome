"""
無信号交差点 交通容量・滞留長 評価 GUI アプリケーション
Streamlit ベースの APS-λ 風インターフェース
"""

import streamlit as st
import pandas as pd
from intersection_analysis import calc_capacity, calc_shared_capacity, calc_queue_length

# ---------------------------------------------------------------------------
# ページ設定
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="無信号交差点 交通容量・滞留長 評価",
    layout="wide",
)

st.title("無信号交差点 交通容量・滞留長 評価")
st.caption("平面交差の計画と設計（2018年版）準拠 ― APS-λ 風解析ツール")

# ---------------------------------------------------------------------------
# セッションステート初期値
# ---------------------------------------------------------------------------
FLOW_LABELS = ["主道路右折", "従道路左折", "従道路直進", "従道路右折"]
DEFAULT_GX = [4.1, 6.9, 6.5, 6.9]
DEFAULT_HX = [2.2, 3.3, 3.5, 3.3]

if "demand" not in st.session_state:
    st.session_state["demand"] = [40, 50, 100, 30]
if "conflict" not in st.session_state:
    st.session_state["conflict"] = [340, 300, 640, 700]
if "gx" not in st.session_state:
    st.session_state["gx"] = list(DEFAULT_GX)
if "hx" not in st.session_state:
    st.session_state["hx"] = list(DEFAULT_HX)
if "V2" not in st.session_state:
    st.session_state["V2"] = 12.0
if "M" not in st.session_state:
    st.session_state["M"] = 150

# ---------------------------------------------------------------------------
# タブ構成
# ---------------------------------------------------------------------------
tab_input, tab_output = st.tabs(["交通量・パラメータ入力", "評価・滞留長出力"])

# =========================================================================
# タブ 1: 交通量・パラメータ入力
# =========================================================================
with tab_input:
    st.subheader("交通流データ")
    st.markdown("各交通流の **需要交通量** と **交錯交通量** を入力してください。")

    # --- 交通流テーブル（st.data_editor） ---
    flow_df = pd.DataFrame(
        {
            "交通流": FLOW_LABELS,
            "需要交通量 (台/時)": st.session_state["demand"],
            "交錯交通量 (台/時)": st.session_state["conflict"],
            "臨界ギャップ gx (秒)": st.session_state["gx"],
            "追従車頭時間 hx (秒)": st.session_state["hx"],
        }
    )

    edited_df = st.data_editor(
        flow_df,
        num_rows="fixed",
        use_container_width=True,
        hide_index=True,
        disabled=["交通流"],
        column_config={
            "交通流": st.column_config.TextColumn(width="medium"),
            "需要交通量 (台/時)": st.column_config.NumberColumn(
                min_value=0, step=1, format="%d"
            ),
            "交錯交通量 (台/時)": st.column_config.NumberColumn(
                min_value=1, step=1, format="%d"
            ),
            "臨界ギャップ gx (秒)": st.column_config.NumberColumn(
                min_value=0.1, step=0.1, format="%.1f"
            ),
            "追従車頭時間 hx (秒)": st.column_config.NumberColumn(
                min_value=0.1, step=0.1, format="%.1f"
            ),
        },
    )

    # セッションステートへ反映
    st.session_state["demand"] = edited_df["需要交通量 (台/時)"].tolist()
    st.session_state["conflict"] = edited_df["交錯交通量 (台/時)"].tolist()
    st.session_state["gx"] = edited_df["臨界ギャップ gx (秒)"].tolist()
    st.session_state["hx"] = edited_df["追従車頭時間 hx (秒)"].tolist()

    st.divider()

    # --- 車線条件 ---
    st.subheader("車線条件（滞留長計算用）")
    col_v2, col_m, col_v1 = st.columns(3)
    with col_v2:
        V2 = st.number_input(
            "大型車混入率 V2 (%)",
            min_value=0.0,
            max_value=100.0,
            value=st.session_state["V2"],
            step=1.0,
            format="%.1f",
        )
        st.session_state["V2"] = V2
    with col_m:
        M = st.number_input(
            "1車線あたりの交通量 M (台/時)",
            min_value=1,
            value=st.session_state["M"],
            step=10,
        )
        st.session_state["M"] = M
    with col_v1:
        V1 = round(100.0 - V2, 2)
        st.metric("乗用車混入率 V1 (%)", f"{V1:.1f}")
        st.caption("※ V1 = 100 − V2 として自動計算")

# =========================================================================
# タブ 2: 評価・滞留長出力
# =========================================================================
with tab_output:
    # ------ 各交通流の読み込み ------
    demands = st.session_state["demand"]
    conflicts = st.session_state["conflict"]
    gx_list = st.session_state["gx"]
    hx_list = st.session_state["hx"]
    V2 = st.session_state["V2"]
    V1 = round(100.0 - V2, 2)
    M = st.session_state["M"]

    # ------------------------------------------------------------------
    # 個別交通流の交通容量計算
    # ------------------------------------------------------------------
    st.subheader("個別交通流の評価")

    cpx_list = []
    ratio_list = []
    judge_list = []

    for i in range(len(FLOW_LABELS)):
        cpx = calc_capacity(conflicts[i], gx_list[i], hx_list[i])
        cpx_list.append(cpx)
        ratio = demands[i] / cpx if cpx > 0 else float("inf")
        ratio_list.append(round(ratio, 3))
        judge_list.append("OK（捌ける）" if ratio < 1.0 else "NG（捌けない）")

    result_df = pd.DataFrame(
        {
            "交通流": FLOW_LABELS,
            "需要交通量 (台/時)": demands,
            "交錯交通量 (台/時)": conflicts,
            "交通容量 Cpx (台/時)": cpx_list,
            "交通容量比": ratio_list,
            "判定": judge_list,
        }
    )

    # 判定列を色付け表示するためスタイル適用
    def highlight_judge(val):
        if val == "OK（捌ける）":
            return "background-color: #d4edda; color: #155724;"
        elif val == "NG（捌けない）":
            return "background-color: #f8d7da; color: #721c24;"
        return ""

    # pandas 2.x では applymap -> map に変更
    _styler_map = getattr(result_df.style, "map", None) or result_df.style.applymap
    styled_df = _styler_map(
        highlight_judge, subset=["判定"]
    ).format({"交通容量比": "{:.3f}"})

    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    st.divider()

    # ------------------------------------------------------------------
    # 混用車線の評価
    # ------------------------------------------------------------------
    st.subheader("混用車線の評価")
    st.markdown(
        "従道路等で **左折＋直進** など複数の交通流が同一車線を共有する場合の"
        "混用車線容量 **Cm** を計算します。"
    )

    shared_options = st.multiselect(
        "混用する交通流を選択してください（2つ以上）",
        options=FLOW_LABELS,
        default=["従道路左折", "従道路直進"],
    )

    if len(shared_options) >= 2:
        idx_list = [FLOW_LABELS.index(label) for label in shared_options]
        shared_wx = [demands[i] for i in idx_list]
        shared_cpx = [cpx_list[i] for i in idx_list]

        Cm = calc_shared_capacity(shared_wx, shared_cpx)
        sum_wx = sum(shared_wx)
        shared_ratio = round(sum_wx / Cm, 3) if Cm > 0 else float("inf")
        shared_judge = "OK（捌ける）" if shared_ratio < 1.0 else "NG（捌けない）"

        shared_detail = pd.DataFrame(
            {
                "交通流": shared_options,
                "需要交通量 (台/時)": shared_wx,
                "交通容量 Cpx (台/時)": shared_cpx,
            }
        )
        st.dataframe(shared_detail, use_container_width=True, hide_index=True)

        col_cm, col_ratio, col_judge = st.columns(3)
        with col_cm:
            st.metric("混用車線容量 Cm (台/時)", Cm)
        with col_ratio:
            st.metric("合計需要 / Cm", f"{shared_ratio:.3f}")
        with col_judge:
            if shared_judge.startswith("OK"):
                st.success(shared_judge)
            else:
                st.error(shared_judge)
    else:
        st.info("混用車線を評価するには交通流を2つ以上選択してください。")

    st.divider()

    # ------------------------------------------------------------------
    # 滞留長の計算
    # ------------------------------------------------------------------
    st.subheader("滞留長の計算")

    Ls = calc_queue_length(M, V1, V2)

    col_ls1, col_ls2, col_ls3 = st.columns(3)
    with col_ls1:
        st.metric("1車線あたり交通量 M", f"{M} 台/時")
    with col_ls2:
        st.metric(
            "車種混入率",
            f"乗用車 {V1:.1f}% / 大型車 {V2:.1f}%",
        )
    with col_ls3:
        st.metric("滞留長 Ls", f"{Ls} m")

    st.caption(
        "Ls = 2 × (M × 60/3600) × ((6 × V1 + 12 × V2) / 100)　"
        "― 平面交差の計画と設計（2018年版）"
    )
