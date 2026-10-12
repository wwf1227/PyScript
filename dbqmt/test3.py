"""
通过 QMT / xtquant 计算股票市盈率（PE）。

xtdata 没有现成的 PE 字段，必须自己算：
    PE(TTM)  = 最新价 * 总股本 / 归母净利润(TTM)
    PE(静态) = 最新价 * 总股本 / 上一个完整年报的归母净利润

要点（xtdata 财务数据的几个坑）：
1. m_timetag(报告期) / m_anntime(公告日) 都是 **字符串 'YYYYMMDD'**，
   不是秒级时间戳，不能用 pd.to_datetime(..., unit='s')。
2. 利润表是**年初至今的累计值**，所以 TTM 要用：
       本期累计 + 上年年报 - 上年同期累计
3. 同一个报告期可能因追溯调整出现多行，按公告日取最后一条。
4. 用 get_instrument_detail 的 TotalVolume 取最新总股本，比 Capital 表口径更即时。
"""

import time
from datetime import datetime

from xtquant import xtdata

# 归母净利润（利润表字段），PershareIndex 里的 s_fa_eps_basic 是按历史股本算的，
# 遇到送转/增发会失真，所以这里从净利润 + 最新股本自己算 EPS。
NET_PROFIT = 'net_profit_excl_min_int_inc'

_income_cache = {}


def _load_income(stock_code, years=4):
    """下载并读取利润表，返回按报告期升序、每个报告期只保留最新公告的 DataFrame。

    下载较慢且财报一天最多变一次，这里按代码缓存，避免 TTM / 年报两次调用重复下载。
    """
    if stock_code in _income_cache:
        return _income_cache[stock_code]

    start = f'{datetime.now().year - years}0101'
    end = datetime.now().strftime('%Y%m%d')

    xtdata.download_financial_data([stock_code], table_list=['Income'],
                                   start_time=start, end_time=end)
    data = xtdata.get_financial_data([stock_code], ['Income'],
                                     start_time=start, end_time=end,
                                     report_type='report_time')

    if not data or stock_code not in data or 'Income' not in data[stock_code]:
        return None

    df = data[stock_code]['Income']
    if df is None or df.empty or NET_PROFIT not in df.columns:
        return None

    df = df[['m_timetag', 'm_anntime', NET_PROFIT]].dropna(subset=[NET_PROFIT])
    # 追溯调整：同一报告期多行时，保留公告日最新的那条
    df = (df.sort_values(['m_timetag', 'm_anntime'])
          .drop_duplicates('m_timetag', keep='last')
          .reset_index(drop=True))
    _income_cache[stock_code] = df if not df.empty else None
    return _income_cache[stock_code]


def get_net_profit_ttm(stock_code):
    """
    归母净利润(TTM)。
    :return: (profit_ttm, 报告期, 公告日)，失败返回 (None, None, None)
    """
    df = _load_income(stock_code)
    if df is None:
        return None, None, None

    profits = dict(zip(df['m_timetag'], df[NET_PROFIT]))
    latest = df.iloc[-1]
    tag = latest['m_timetag']
    year, mmdd = int(tag[:4]), tag[4:]

    if mmdd == '1231':  # 年报本身就是完整 12 个月
        return float(latest[NET_PROFIT]), tag, latest['m_anntime']

    last_annual = profits.get(f'{year - 1}1231')
    last_same = profits.get(f'{year - 1}{mmdd}')
    if last_annual is None or last_same is None:
        print(f'{stock_code} 缺少上年同期({year - 1}{mmdd})或上年年报数据，无法算 TTM')
        return None, None, None

    ttm = float(latest[NET_PROFIT]) + float(last_annual) - float(last_same)
    return ttm, tag, latest['m_anntime']


def get_net_profit_annual(stock_code):
    """最近一个完整年报的归母净利润，用于静态 PE。"""
    df = _load_income(stock_code)
    if df is None:
        return None, None
    annual = df[df['m_timetag'].str.endswith('1231')]
    if annual.empty:
        return None, None
    row = annual.iloc[-1]
    return float(row[NET_PROFIT]), row['m_timetag']


def get_last_price(stock_code):
    """最新价：优先盘口 tick，非交易时段回落到最近一根日线收盘价。"""
    try:
        tick = xtdata.get_full_tick([stock_code]).get(stock_code) or {}
        price = tick.get('lastPrice')
        if price:
            return float(price)
    except Exception:
        pass

    kline = xtdata.get_market_data(['close'], [stock_code], period='1d', count=1)
    close = kline['close']
    if not close.empty:
        return float(close.iloc[0, -1])

    detail = xtdata.get_instrument_detail(stock_code) or {}
    return float(detail.get('PreClose') or 0) or None


def get_pe(stock_code):
    """
    计算市盈率。
    :return: dict，含 PE(TTM)、静态 PE、EPS 等；数据缺失的字段为 None。
    """
    detail = xtdata.get_instrument_detail(stock_code) or {}
    name = detail.get('InstrumentName')
    total_shares = float(detail.get('TotalVolume') or 0)
    price = get_last_price(stock_code)

    result = {
        'code': stock_code, 'name': name, 'price': price,
        'total_shares': total_shares,
        'net_profit_ttm': None, 'eps_ttm': None, 'pe_ttm': None,
        'net_profit_annual': None, 'eps_annual': None, 'pe_static': None,
        'report_date': None, 'announce_date': None, 'annual_report_date': None,
    }
    if not price or not total_shares:
        print(f'{stock_code} 缺少最新价或总股本')
        return result

    profit_ttm, tag, ann = get_net_profit_ttm(stock_code)
    if profit_ttm:
        eps = profit_ttm / total_shares
        result.update(net_profit_ttm=profit_ttm, eps_ttm=round(eps, 4),
                      # 亏损股 PE 无意义，置 None
                      pe_ttm=round(price / eps, 2) if eps > 0 else None,
                      report_date=tag, announce_date=ann)

    profit_annual, annual_tag = get_net_profit_annual(stock_code)
    if profit_annual:
        eps_a = profit_annual / total_shares
        result.update(net_profit_annual=profit_annual, eps_annual=round(eps_a, 4),
                      pe_static=round(price / eps_a, 2) if eps_a > 0 else None,
                      annual_report_date=annual_tag)

    return result


def load_fundamentals(stock_codes):
    """
    一次性取回各股的基本面（股本 + TTM/年报净利润 + EPS）。
    这些数据一天最多变一次，轮询时不必重复下载，所以单独抽出来预加载。
    """
    fundamentals = {}
    for code in stock_codes:
        detail = xtdata.get_instrument_detail(code) or {}
        shares = float(detail.get('TotalVolume') or 0)

        profit_ttm, tag, ann = get_net_profit_ttm(code)
        profit_annual, annual_tag = get_net_profit_annual(code)

        fundamentals[code] = {
            'name': detail.get('InstrumentName') or code,
            'total_shares': shares,
            'eps_ttm': profit_ttm / shares if profit_ttm and shares else None,
            'eps_annual': profit_annual / shares if profit_annual and shares else None,
            'report_date': tag, 'announce_date': ann, 'annual_report_date': annual_tag,
        }
    return fundamentals


def watch(stock_codes, interval=3):
    """
    每 interval 秒刷新一次最新价并输出 PE 到控制台。Ctrl+C 结束。
    """
    print(f'预加载基本面数据（{len(stock_codes)} 只）...')
    fundamentals = load_fundamentals(stock_codes)
    for code, f in fundamentals.items():
        print(f"  {code} {f['name']} 总股本={f['total_shares']:,.0f} "
              f"EPS(TTM)={f['eps_ttm'] and round(f['eps_ttm'], 4)} 报告期={f['report_date']}")
    print(f'开始轮询，每 {interval} 秒一次，Ctrl+C 退出\n')

    try:
        while True:
            # 一次调用批量取全部代码的盘口，避免逐只请求
            try:
                ticks = xtdata.get_full_tick(stock_codes) or {}
            except Exception as e:
                print(f'[{datetime.now():%H:%M:%S}] 行情获取失败: {e}')
                time.sleep(interval)
                continue

            # print(f'--- {datetime.now():%Y-%m-%d %H:%M:%S} ---')
            for code in stock_codes:
                f = fundamentals[code]
                price = (ticks.get(code) or {}).get('lastPrice')
                if not price:
                    print(f"{code} {f['name']} 无最新价")
                    continue

                eps_ttm, eps_annual = f['eps_ttm'], f['eps_annual']
                # 亏损股 PE 无意义，显示 '亏损'
                pe_ttm = round(price / eps_ttm, 2) if eps_ttm and eps_ttm > 0 else '亏损'
                pe_static = round(price / eps_annual, 2) if eps_annual and eps_annual > 0 else '亏损'
                print(f"{code} {f['name']:<8} 价格={price:>9.2f}  " f"PE(TTM)={pe_ttm:>8}  PE(静态)={pe_static:>8}")
            print()
            time.sleep(interval)
    except KeyboardInterrupt:
        print('已停止')


if __name__ == '__main__':
    watch(['300308.SZ'], interval=3)
