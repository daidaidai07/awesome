"""
無信号交差点の交通容量・滞留長評価プログラム
日本の『平面交差の計画と設計（2018年版）』準拠
"""

import math


def calc_capacity(Qx_hourly, gx, hx):
    """横断可能容量を計算する。

    Args:
        Qx_hourly: 交錯交通量 (台/時)
        gx: 臨界ギャップ (秒)
        hx: 追従車頭時間 (秒)

    Returns:
        交通容量 Cpx (台/時, 小数点以下四捨五入)
    """
    Qx = round(Qx_hourly / 3600.0, 4)  # 台/秒に変換（小数第4位まで）
    Cx = Qx * math.exp(-Qx * gx) / (1.0 - math.exp(-Qx * hx))
    Cpx = Cx * 3600.0
    return round(Cpx)


def calc_shared_capacity(Wx_list, Cpx_list):
    """混用車線の交通容量を計算する。

    Args:
        Wx_list: 各方向の需要交通量のリスト (台/時)
        Cpx_list: 各方向の横断可能容量のリスト (台/時)

    Returns:
        混用車線の交通容量 Cm (台/時, 小数点以下四捨五入)
    """
    sum_Wx = sum(Wx_list)
    sum_Wx_over_Cpx = sum(w / c for w, c in zip(Wx_list, Cpx_list))
    Cm = sum_Wx / sum_Wx_over_Cpx
    return round(Cm)


def calc_queue_length(M, V1, V2):
    """滞留長を計算する。

    Args:
        M: 1車線あたりの交通量 (台/時)
        V1: 乗用車混入率 (%)
        V2: 大型車混入率 (%)

    Returns:
        滞留長 Ls (m, 小数第1位まで)
    """
    Ls = 2.0 * (M * (60.0 / 3600.0)) * ((6.0 * V1 + 12.0 * V2) / 100.0)
    return round(Ls, 1)


if __name__ == "__main__":
    print("=" * 60)
    print("無信号交差点 交通容量・滞留長 評価")
    print("=" * 60)

    # テストケース1: No.1 主道路からの右折
    Qx1 = 40 + 300  # 340 台/時
    result1 = calc_capacity(Qx1, gx=4.1, hx=2.2)
    expected1 = 1231
    print(f"\n【テストケース1: No.1 主道路からの右折】")
    print(f"  交錯交通量: {Qx1} 台/時")
    print(f"  臨界ギャップ: 4.1 秒, 追従車頭時間: 2.2 秒")
    print(f"  交通容量: {result1} 台/時 (想定: {expected1} 台/時)")
    print(f"  判定: {'OK' if result1 == expected1 else 'NG'}")

    # テストケース2: No.2 従道路からの左折
    Qx2 = 300  # 300 台/時
    result2 = calc_capacity(Qx2, gx=6.9, hx=3.3)
    expected2 = 702
    print(f"\n【テストケース2: No.2 従道路からの左折】")
    print(f"  交錯交通量: {Qx2} 台/時")
    print(f"  臨界ギャップ: 6.9 秒, 追従車頭時間: 3.3 秒")
    print(f"  交通容量: {result2} 台/時 (想定: {expected2} 台/時)")
    print(f"  判定: {'OK' if result2 == expected2 else 'NG'}")

    # テストケース3: 従道路の左折・直進混用車線
    Wx_list = [50, 100]
    Cpx_list = [702, 356]
    result3 = calc_shared_capacity(Wx_list, Cpx_list)
    expected3 = 426
    print(f"\n【テストケース3: 従道路の左折・直進混用車線】")
    print(f"  左折: {Wx_list[0]} 台/時 (Cpx={Cpx_list[0]}), "
          f"直進: {Wx_list[1]} 台/時 (Cpx={Cpx_list[1]})")
    print(f"  混用車線容量: {result3} 台/時 (想定: {expected3} 台/時)")
    print(f"  判定: {'OK' if result3 == expected3 else 'NG'}")

    # テストケース4: 滞留長（直進等車線）
    M = 150
    V1 = 88.00
    V2 = 12.00
    result4 = calc_queue_length(M, V1, V2)
    expected4 = 33.6
    print(f"\n【テストケース4: 滞留長（直進等車線）】")
    print(f"  交通量: {M} 台/時, 乗用車率: {V1}%, 大型車率: {V2}%")
    print(f"  滞留長: {result4} m (想定: {expected4} m)")
    print(f"  判定: {'OK' if result4 == expected4 else 'NG'}")

    # 総合判定
    print("\n" + "=" * 60)
    all_ok = (result1 == expected1 and result2 == expected2
              and result3 == expected3 and result4 == expected4)
    print(f"総合判定: {'全テストOK' if all_ok else 'NGあり'}")
    print("=" * 60)
