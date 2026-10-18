# Failed Strategies

[![ci](https://github.com/pham-canh/failed-strategies/actions/workflows/ci.yml/badge.svg)](https://github.com/pham-canh/failed-strategies/actions/workflows/ci.yml) ![license](https://img.shields.io/badge/license-MIT-green)

Bộ sưu tập các chiến lược giao dịch futures ĐÃ THẤT BẠI trong backtest — lưu lại kèm post-mortem chi tiết: **lỗ ở đâu, tại sao lỗ**, và bài học rút ra. Đây là tài liệu tham khảo để KHÔNG lặp lại sai lầm, không phải code để dùng thật.

---

## English summary

Six Binance-futures strategies that **failed** in backtest, kept with a post-mortem for each: what broke, why, and what it teaches. This is reference material for avoiding repeat mistakes — not production code. The full post-mortems below are in Vietnamese; this section is the English map.

**Backtest setup (mandatory context):**

- **Window:** full 18 months, `20250201–20260801`, timeframe **1h**, 43-coin universe (`universe.json`), Binance futures.
- **Only the freqtrade engine is trusted.** Vectorized sim numbers were used only for screening; the sim guessed wrong repeatedly, so every headline figure below is a `freqtrade backtesting` run.
- **⚠️ The window is strongly bear-biased.** Essentially all profit in this period came from the **short** side. A long uptrend would change the picture. There is no out-of-window data.

**Results:**

| Strategy         | PnL (USDT)  | Sharpe | Max DD      | Verdict                                                        |
| ---------------- | ----------- | ------ | ----------- | -------------------------------------------------------------- |
| FundingSmoothTrend | **−621.0**  | —      | 697.2 (68%) | ❌ Long-only trend-following dies in a bear market             |
| XSMom              | +15.2       | 0.03   | 431.4 (43%) | ❌ Cross-sectional momentum — return not worth the drawdown   |
| TsMom              | +3.4        | 0.01   | 196.1       | ❌ Long-only momentum is ~flat                                 |
| LowVol             | +57.7       | 0.16   | 402.1       | ❌ Funding tax consumes ~52% of gross profit                   |
| Carry              | +4852 (sim) | —      | —           | ❌ **Not implementable futures-only** (needs a spot leg)       |
| PairsDyn           | −525.0      | −3.23  | —           | ❌ Rolling pair selection loses in every variant tried         |

**Three lessons that repeat across almost every strategy above:**

1. **Long-only dies in a bear market.** Every strategy that won here has either a regime filter or a short leg.
2. **A loose signal is just noise.** Tightening exits, resampling pairs, and resetting EWM state all destroyed the edge rather than adding to it.
3. **The edge is concentrated and does not generalise.** Ten different pair-selection methods were swept and all lost. Correlation tightness turned out to be unrelated to profitability.

**How to reproduce:** see [Cách chạy lại](#cách-chạy-lại) below.

---

## Bối cảnh kiểm định (bắt buộc đọc)

- **Cửa sổ:** FULL 18 tháng `20250201–20260801`, khung **1h**, universe 43 coin (`universe.json`), Binance futures.
- **Chỉ tin freqtrade engine** (`freqtrade backtesting`). Các con số từ sim vectorized chỉ dùng để sàng lọc — nhiều lần sim đoán sai (xem `Carry`, `PairsDyn`), engine mới là chuẩn.
- **⚠️ Thiên vị bear window cực mạnh:** toàn bộ lợi nhuận trong kỳ này đến từ **short**. Một uptrend dài sẽ thay đổi cục diện. Chưa có dữ liệu ngoài window này.
- Bài học chung lặp lại ở hầu hết các strategy dưới đây: **long-only chết trong bear**, **tín hiệu quá lỏng = nhiễu**, và **edge tập trung, không nhân rộng được bằng cách thay đổi cách chọn tín hiệu/cặp**.

## Tổng quan kết quả

| Chiến lược         | PnL (USDT)  | Sharpe | Max DD      | Verdict                                          |
| ------------------ | ----------- | ------ | ----------- | ------------------------------------------------ |
| FundingSmoothTrend | **−621.0**  | —      | 697.2 (68%) | ❌ Long-only trend-following chết trong bear     |
| XSMom              | +15.2       | 0.03   | 431.4 (43%) | ❌ Momentum cross-section, lãi không đáng rủi ro |
| TsMom              | +3.4        | 0.01   | 196.1       | ❌ Long-only momentum gần như 0 lời              |
| LowVol             | +57.7       | 0.16   | 402.1       | ❌ Funding tax ăn ~52% lợi nhuận                 |
| Carry              | +4852 (sim) | —      | —           | ❌ **Bất khả thi futures-only** (cần chân spot)  |
| PairsDyn           | −525.0      | −3.23  | —           | ❌ Rolling pairs lỗ mọi variant                  |

So sánh với các chiến lược ĐÃ THÀNH CÔNG (repo `crypto-quant-strategies`): BAB +221, ShortRev +298, PairsArb +262 (Sharpe 1.52), FundingCapture +1433. Thất bại không phải vì ý tưởng thiếu học thuật — mà vì ý tưởng không khớp cấu trúc thị trường crypto futures.

---

## 1. FundingSmoothTrend — Trend-following EMA + ADX filter

**Ý tưởng:** EMA 20/60 long-only, chỉ vào khi ADX(14) > 25 — "chỉ theo trend thật, không theo nhiễu". Cải tiến so với trend-following classic (EMA 13/80, win 21%, lỗ −0.87%/lệnh).

**Kết quả:** **−621.0 USDT, max DD 697.2 (68%)** — tồi tệ nhất trong cả 6.

**Lỗ ở đâu:**

- **Long-only trong thị trường bear 18 tháng** = bắt dao rơi liên tục. ADX filter không cứu được vì ADX cao chỉ báo trend đang diễn ra — mà trend ở đây là trend XUỐNG.
- Không có chân short, không có bộ lọc regime (như `BTC > SMA`), không có funding filter.
- EMA trend-following mua đỉnh khi momentum lên cao nhất — đúng lúc thị trường đảo chiều.

**Bài học:** Trend-following đơn thuần (chỉ kỹ thuật, không có góc nhìn funding/cấu trúc) không có edge ở crypto futures 1h. Mọi chiến lược thắng đều có bộ lọc regime/short leg. Xác nhận đánh giá tài liệu ngoài là SAI khi đánh giá cao hướng này.

## 2. XSMom — Cross-sectional momentum (Jegadeesh & Titman 1993)

**Ý tưởng:** Xếp hạng 43 coin theo return LOOKBACKh; long top 20% (rank > 0.80), short bottom 20% (rank < 0.20). Long/short cùng lúc → market-neutral-ish. Exit khi rank hồi về 0.4–0.6.

**Kết quả:** +15.2 USDT, **Sharpe 0.03**, DD 431.4 (43%). Lợi nhuận không đáng rủi ro.

**Lỗ ở đâu:**

- **Chân long lỗ −396, chân short thắng +298** — momentum long side là gánh nặng ròng. Trong uptrend tháng, XSMom shorts lỗ MỌI tháng (cơ chế squeeze có thật).
- Bản chất "rank top 20%" vẫn là **đặt cược trend 1 phía của coin** — hết pha pump là chạm nóc, đúng lúc short side thắng → long lỗ.
- Đã thêm REGIME filter (long chỉ khi BTC uptrend) nhưng không cứu được.

**Bài học:** Cross-sectional momentum không phải "market neutral" khi crypto cùng di chuyển 1 chiều (correlation nền 0.51–0.65 mọi khung). Lợi nhuận momentum nằm ở **short side khi BTC bear** — về bản chất trùng họ với FundingCapture/ShortRev, không thêm đa dạng hóa (tương quan ~0.1). **Thêm vào danh mục chỉ hạ Sharpe.**

## 3. TsMom — Time-series momentum (Moskowitz, Ooi & Pedersen 2012)

**Ý tưởng:** Long coin tăng ≥ 40% trong 28 ngày (LOOKBACK 672h), chỉ khi BTC trên SMA 168h. Exit qua max-hold 14 ngày + static stop.

**Kết quả:** +3.4 USDT, **Sharpe 0.01**, DD 196.1.

**Lỗ ở đâu:**

- **Long-only momentum trong bear = gần như không có cơ hội.** Threshold MIN_RET 40% hiếm khi đạt và khi đạt thì đã là cuối pha pump.
- Tương quan âm với danh mục (−0.16) nhưng "âm mà vô dụng" — thêm vào không cải thiện gì vì bản thân gần như không giao dịch có lời.

**Bài học:** Cùng họ "momentum" nhưng time-series (đặt cược trend 1 coin theo chính nó) kém hơn cross-sectional (đặt cược so sánh tương đối giữa các coin). Cả hai đều thua short-momentum trong bear window.

## 4. LowVol — Low volatility anomaly (Ang, Hodrick, Xing & Zhang 2006)

**Ý tưởng:** Coin volatility cao → lợi nhuận thấp (được định giá quá cao bởi nhà đầu tư "mua xổ số"). Short coin vol cao nhất (rank > 0.80), long coin vol thấp nhất (rank < 0.20). Nghiên cứu cho thấy long low-vol là drag → mặc định **short-only**.

**Kết quả:** +57.7 USDT, Sharpe 0.16, **DD 402.1 (40%)**.

**Lỗ ở đâu:**

- **Funding tax ăn ~52% lợi nhuận** — short coin high-vol trong 1h futures phải trả funding liên tục; phần thưởng price PnL không bù đủ.
- **DD 40% cho +58 USDT** — risk-adjusted quá tệ. Cùng họ short nhưng không có bộ lọc chống squeeze như FundingCapture.
- Volatility không phải tín hiệu ổn định: high-vol coin dễ bị squeeze (short lại đúng đám crowd cuối).

**Bài học:** Low-vol anomaly không chuyển thành edge net sau funding ở crypto futures. Mọi chiến lược short cần **bộ lọc trend per-coin** (chặn short khi giá đang trên EMA — chính là TREND filter của FundingCapture) để tránh squeeze.

## 5. Carry — Funding carry (Koijen, Moskowitz, Pedersen & Vrugt 2018)

**Ý tưởng:** Carry của crypto futures = funding rate. Funding dương TB → short nhận funding; funding âm TB → long. Không cần threshold nổi bật.

**Kết quả:** **+4852 USDT (sim delta-neutral)** NHƯNG — mục tiêu gốc là **long spot + short perp** (delta-neutral).

**Lỗ ở đâu:**

- **BẤT KHẢ THI trên freqtrade futures-only**: freqtrade chỉ có chân futures. Không có chân **spot** để tạo vị thế delta-neutral → long leg bị bỏ lửng, hứng toàn bộ rủi ro giá.
- Đã tự kiểm chứng bằng một backtest scratch dùng spot (giả lập giá spot bằng giá perp trên cùng khung thời gian): +4852 USDT chỉ tồn tại **khi có spot leg**. Futures-only thì không. Script scratch đó **không nằm trong repo này** — repo này chỉ chứa những gì chạy được trên freqtrade futures.
- (Bản `Carry.py` này chỉ short coin funding dương → đây thực chất là **short-momentum không bộ lọc**, không phải carry thuần.)

**Bài học:** Funding-carry delta-neutral là ý tưởng học thuật hợp lý nhưng **không chạy được trong kiến trúc futures-only của freqtrade**. Cần sàn khác có spot+perp đồng thời (hoặc dùng FundingCapture short-only với bộ lọc — đã chứng minh lời +424).

## 6. PairsDyn — Pairs trading rolling (dynamic cointegration)

**Ý tưởng:** Thay 11 cặp tĩnh bằng bộ cặp **rolling**: mỗi tuần chọn lại cặp cointegrated từ cửa sổ formation mới nhất (`pairs_dyn.json`). Long A + short B cùng vốn, vào khi |z| > 2, thoát khi z về 0.

**Kết quả:** **−525.0 USDT, Sharpe −3.23, PF 0.88, win 39.7%** (48h formation/6h rescan). Lỗ mọi variant: SPAN12 (Sharpe 0.05), mọi EXIT_Z 0.5–1.5, mọi cách reset EWM.

**Lỗ ở đâu:**

- **Cointegration tìm được trong quá khứ không còn đúng tương lai** — 75% lệnh chết ở stop_loss −10%, winners hiếm. Churn 13 lệnh/ngày = 7128 lệnh toàn nhiễu.
- **Corr-tightness ≠ edge**: cặp static THẮNG có corr rolling chỉ 0.68–0.73 và **gần như không bao giờ vào top-11 động** (chỉ 2–3% số scan) — cặp "khít" corr 0.89–0.94 được chọn lại lỗ.
- **ADF cửa sổ ngắn là nhiễu thuần**: ở 24–48h, random pair có p<0.05 tới 25–28% (nominal 5%) → chọn cặp theo ADF ngắn hạn = chọn theo xác suất. Edge thật chỉ có ở EG p<0.001 trên 2000 bar (83 ngày).
- PCA+K-Means clustering cũng fail: within-cluster ADF ≈ random, cluster membership Jaccard @+24h chỉ 0.19–0.25 (narrative đổi gần như hoàn toàn mỗi ngày).

**Bài học:** **Edge tập trung, không nhân rộng được.** Nới lỏng tín hiệu, đổi cách chọn cặp (10 phương pháp sweep đều thua), hay chọn cặp động ngắn hạn đều phá edge. Static EWM thích nghi liên tục trên 11 cặp EG p<0.001 là thiết kế đúng — giữ nguyên.

---

## Cách chạy lại

Mọi đường dẫn đều **ghi đè được bằng biến môi trường**, không cái nào ghi cứng vào mã nguồn. Mặc định trỏ vào repo này (`universe.json`, `pairs_dyn.json` ở root) và `user_data/data/binance/futures` tương đối.

```bash
# Data dir (feather files từ freqtrade download-data --include-initial-candle)
export FT_DATA_DIR=/path/to/user_data/data/binance/futures   # mặc định: user_data/data/binance/futures
# Universe (chỉ XSMom, LowVol)
export FT_UNIVERSE=/path/to/universe.json                     # mặc định: <repo>/universe.json
# Pairs file (chỉ PairsDyn)
export FT_PAIRS=/path/to/pairs_dyn.json                       # mặc định: <repo>/pairs_dyn.json
# Sweep tuning file, dùng bởi Carry / XSMom / TsMom / PairsDyn. TUỲ CHỌN:
# không có thì strategy chạy với default của chính nó.
export FT_SWEEP=/path/to/sweep.json                           # mặc định: /tmp/ft_sweep.json
#   (PairsDyn trước đây chỉ đọc PA_SWEEP — vẫn còn hỗ trợ, và thắng nếu cả hai
#    đều được đặt.)

freqtrade backtesting -s XSMom --timeframe 1h --timerange 20250201-20260801 \
  --dataformat-ohlcv feather -c your-config.json
```

Các hằng số sweep có thể override qua `/tmp/ft_sweep.json` (xem header từng file).

## Những gì KHÔNG làm trong repo này

- `FundingCapture.py`, `BAB.py`, `PairsArb.py`, `ShortRev.py` — các chiến lược THÀNH CÔNG, nằm ở repo riêng (`crypto-quant-strategies`).
- Data feather (không commit dữ liệu lớn) — cần tự `freqtrade download-data`.
