"""Readable, offline results generated from recorded measurements; no services queried."""
import argparse
import csv
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLE = """+:root{color-scheme:light;--ink:#102a43;--muted:#52677c;--blue:#155e75;--line:#dce5ec}
*{box-sizing:border-box}body{margin:0;background:#f3f6f8;color:var(--ink);font:16px/1.65 system-ui,sans-serif}
main{max-width:1120px;margin:auto;padding:40px 24px}h1{font-size:clamp(30px,5vw,46px);line-height:1.15;letter-spacing:-1.5px;margin:12px 0 18px}h2{font-size:25px;margin:0 0 18px}h3{font-size:18px;margin:22px 0 10px}
p{margin:10px 0}.muted,small{color:var(--muted)}a{color:var(--blue);text-underline-offset:3px}section,.card{background:white;border:1px solid var(--line);border-radius:16px;padding:26px;margin:22px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:16px}.grid .card{margin:0}.metric{font-size:31px;font-weight:750;line-height:1.2;display:block;margin:9px 0}.good{color:#146044}.warn{color:#985c00}.bad{color:#ae3030}.tag{display:inline-block;border-radius:20px;padding:3px 12px;background:#e6f3ef;color:#146044;font-size:14px;font-weight:650}.tag.warn{background:#fff3d6;color:#805000}nav{display:flex;flex-wrap:wrap;gap:18px;margin:22px 0}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:11px 12px;border-bottom:1px solid var(--line)}th{background:#f4f7fa}td.num{text-align:right;font-variant-numeric:tabular-nums}.scroll{overflow-x:auto}code{background:#edf2f7;padding:2px 5px;border-radius:4px}li{margin:7px 0}.barline{display:grid;grid-template-columns:150px 1fr 80px;align-items:center;gap:14px;margin:12px 0}.track{height:14px;border-radius:8px;background:#edf2f7;overflow:hidden}.bar{height:100%;background:#155e75;border-radius:8px}.bar.amber{background:#d49a39}.bar.gray{background:#7890a5}.lead{max-width:850px;font-size:18px}.flow{display:flex;flex-wrap:wrap;gap:10px}.flow span{background:#edf5f7;border:1px solid #c9dde3;border-radius:8px;padding:10px 14px}details{margin-top:20px}summary{cursor:pointer;font-weight:650}footer{margin:30px 0;color:var(--muted);font-size:13px}@media(max-width:600px){main{padding:24px 14px}section,.card{padding:18px}.barline{grid-template-columns:105px 1fr 65px;font-size:13px}}@media print{body{background:white}main{max-width:none;padding:0}section,.card{break-inside:avoid}nav{display:none}a{color:inherit}}
"""


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def load(root):
    benchmarks = read_csv(root / "docs/data/db-benchmark.csv")
    # Verify plotted/table values against original benchmark output, rather than
    # trusting a presentation table. Historical raw files are never rewritten.
    for row in benchmarks:
        prefix = "bppb_v2_" if row["variant"] == "v2" else "bppb_"
        source = read_json(root / "evidence/benchmark" / (prefix + row["scale"]) / "summary.json")
        for mode in ("B", "P"):
            actual = next(item for item in source["median_between_runs"] if item["mode"] == mode and item["scenario"] == row["scenario"])
            for field in ("p50_ms", "p95_ms", "throughput_rps", "error_rate"):
                if abs(float(row[mode + "_" + field]) - actual[field]) > 1e-8:
                    raise ValueError("Recorded benchmark table differs from measurement")
    runs = []
    for path in sorted((root / "evidence/reproduction").glob("*/summary.json")):
        item = read_json(path)
        if item.get("source_rows") == 734:
            browser_path = path.parent / "browser.json"
            browser = read_json(browser_path) if browser_path.exists() else {}
            runs.append({"id": path.parent.name, "passed": item["passed"], "stages": item["stages"],
                         "browser_checks": len(browser.get("checks", {})), "transport": item.get("transport"),
                         "checked_at_utc": item.get("checked_at_utc"), "path": path.relative_to(root).as_posix()})
    return {"benchmarks": benchmarks, "runs": runs,
            "scanner": read_json(root / "evidence/scanner/evaluation_v1_2.json"),
            "leakage": read_csv(root / "docs/data/leakage.csv"),
            "resources": read_csv(root / "docs/data/v2-resources.csv"),
            "residual": read_csv(root / "docs/data/residual.csv"),
            "deployment": read_json(root / "evidence/acceptance/deployed-login-health.json"),
            "deployed_accounts": read_json(root / "evidence/acceptance/deployed-evaluator-accounts.json"),
            "storage": read_json(root / "evidence/migration/1m/completion.json")["database_size_bytes"],
            "backup": read_json(root / "evidence/backup/backup-report.json"),
            "restore": read_json(root / "evidence/backup/restore-report.json")}


def number(value, places=2):
    return f"{float(value):,.{places}f}"


def table(headers, rows):
    return '<div class="scroll"><table><thead><tr>' + ''.join('<th>' + escape(str(v)) + '</th>' for v in headers) + \
        '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + escape(str(v)) + '</td>' for v in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def run_page(report):
    """Per-execution summary: stages and outcomes, with machine evidence nearby."""
    passed = report.get("passed", False)
    rows = [(name.replace('_', ' ').title(), value.get('status', 'NOT_RUN'),
             value.get('rows_compared', value.get('rows', value.get('accounts', value.get('checks', '')))))
            for name, value in report.get("stages", {}).items()]
    return '<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hasil verifikasi 734 record</title><style>' + STYLE + '</style><main><small>HASIL EKSEKUSI</small><h1>Verifikasi 734 record</h1><p class="metric ' + ('good' if passed else 'bad') + '">' + ('LULUS' if passed else 'GAGAL') + '</p><p>Transport: ' + escape(report.get('transport', 'belum tersedia')) + '</p>' + table(('Tahap', 'Hasil', 'Jumlah'), rows) + '<section><h2>Cara membaca</h2><p>PASS berarti tahap memenuhi pemeriksaan yang dijalankan. FAIL berarti ada pemeriksaan atau prasyarat yang gagal. NOT_RUN berarti belum dijalankan. Keberhasilan ini berlaku pada lingkungan dan populasi run tersebut.</p><p>Rincian mesin: <a href="summary.json">ringkasan</a>, <a href="migration.json">validasi migrasi</a>, <a href="security.json">keamanan</a>, <a href="browser.json">enam akun di browser</a>.</p></section></main></html>'


def render(data):
    good_runs = [item for item in data["runs"] if item["passed"]]
    scanner = data["scanner"]
    bidx_rows = [row for row in data["benchmarks"] if row["scenario"] == "read_by_nik" and row["variant"] == "v2"]
    chart = ''
    for row in bidx_rows:
        before, after = float(row['B_p95_ms']), float(row['P_p95_ms'])
        chart += '<h3>' + escape(row['scale']) + ' record — pencarian NIK</h3>'
        for label, value, style in [('Plaintext', before, 'gray'), ('Terproteksi', after, 'amber')]:
            chart += '<div class="barline"><span>' + label + '</span><div class="track"><div class="bar ' + style + '" style="width:' + str(100 * value / max(before, after)) + '%"></div></div><strong>' + number(value) + ' ms</strong></div>'
    benchmark_rows = [(r['scale'], r['scenario'], number(r['B_p50_ms']), number(r['P_p50_ms']), number(r['B_p95_ms']), number(r['P_p95_ms']), number(r['B_throughput_rps']), number(r['P_throughput_rps'])) for r in data['benchmarks'] if r['variant'] == 'v2']
    leakage_rows = [(r['dataset'], r['scenario'], number(r['ESCE_percent']) + '%', number(r['DIE_percent']) + '%') for r in data['leakage']]
    resource_rows = [(r['scale'], r['scenario'], number(r['client_cpu_percent_one_core_median'])+'%', number(float(r['client_ram_bytes_peak'])/1048576)+' MiB', number(r['db_cpu_percent_one_core_median'])+'%', number(float(r['db_ram_bytes_peak'])/1048576)+' MiB', number(float(r['openbao_ram_bytes_peak'])/1048576)+' MiB') for r in data['resources'] if r['mode'] == 'P']
    run_rows = [(r['id'], 'PASS' if r['passed'] else 'FAIL', r['transport'], r['browser_checks']) for r in data['runs']]
    storage_rows = [(scale, number(data['storage']['baseline_' + scale] / 1048576),
                     number(data['storage']['protected_' + scale] / 1048576),
                     number(data['storage']['protected_' + scale] / data['storage']['baseline_' + scale]) + '×')
                    for scale in ('100k', '1m')]
    browser_count = good_runs[-1]['browser_checks'] if good_runs else 0
    deployed = data['deployment']
    deployment_status = '<p class="warn"><strong>Login browser deployment belum lulus pada pemeriksaan terbaru.</strong> Halaman HTTPS tersedia, tetapi autentikasi dengan Origin URL publik ditolak HTTP403. Diagnostik non-browser dengan akun yang sama berhasil; indikasi ketidakcocokan Origin runtime. Operator perlu menyamakan APP_ORIGIN dengan URL akses dan me-restart layanan terkait. Ini bukan hasil gagal kredensial dan tidak diatasi dengan mematikan CSRF/TLS. <a href="../evidence/acceptance/deployed-origin-diagnosis.json">Bukti diagnostik</a>.</p>' if data['deployed_accounts']['status'] != 'PASSED' else '<p class="good"><strong>Uji enam akun deployment terbaru lulus.</strong></p>'
    parts = ['<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hasil Pelindungan Data Pribadi</title><style>', STYLE, '</style></head><body><main>',
             '<small>HASIL TEKNIS • TIM BOGAGOL</small><h1>Data bocor, nilai sensitif<br>tetap dibatasi.</h1><p class="lead">Sistem menemukan data pribadi, mengenkripsi field sensitif, melayani pengguna sesuai kewenangan, dan memulihkan layanan dari backup. Halaman ini menjelaskan hasil pengujian beserta batasnya.</p>',
             '<nav><a href="#security">Keamanan</a><a href="#service">Aplikasi</a><a href="#performance">Kinerja</a><a href="#limits">Keterbatasan</a><a href="../README.md">Panduan penggunaan</a></nav>',
             '<div class="grid"><div class="card"><small>DATA SUMBER</small><span class="metric">734 record</span>29 kolom, tanpa menghapus field sumber</div><div class="card"><small>PERLINDUNGAN</small><span class="metric">25 field</span>AES-256-GCM; 3 blind index untuk exact lookup</div><div class="card"><small>AKSES PENGGUNA</small><span class="metric">6 peran</span>Record dan field dibatasi oleh backend</div></div>',
             '<section><h2>Cara kerja sistem</h2><div class="flow"><span>1. Assessment</span><span>2. Profile perlindungan</span><span>3. Migrasi terenkripsi</span><span>4. Aplikasi HTTPS</span><span>5. Verifikasi & pemulihan</span></div><p>Database menyimpan ciphertext untuk identitas dan keuangan. Kunci disimpan terpisah di OpenBao. Pengguna sah menerima field yang sesuai perannya; analis menerima agregat berukuran minimal 5.</p></section>',
             '<section id="security"><span class="tag">TERBUKTI DALAM SCOPE UJI</span><h2>Perlindungan dan pemulihan</h2><ul><li>734 record dan seluruh field dibandingkan kembali dengan sumber di memori; NULL dan nol awal dipertahankan. Run ulang tidak menggandakan record.</li><li>Perubahan bit dan penukaran ciphertext antar-record/kolom ditolak. Tidak ada fallback plaintext.</li><li>Role analis ditolak membaca tabel/view per record. Koneksi protected tanpa TLS dan hostname salah ditolak.</li><li>Backup terenkripsi dapat di-restore; perubahan satu byte ditolak. Record sintetis yang dihapus tidak muncul pada backup baru.</li><li>Restore tanpa OpenBao mempertahankan ciphertext; restore dengan akses kunci diuji kembali melalui aplikasi.</li></ul>',
             '<h3>Simulasi salinan data bocor</h3><p>ESCE adalah persentase sel sensitif non-NULL yang berhasil dipulihkan persis. DIE adalah persentase record dengan pengenal langsung yang terungkap. Penyebut ESCE hanya 25 field AEAD, bukan seluruh isi database.</p>', table(('Dataset', 'Kemampuan penyerang', 'ESCE', 'DIE'), leakage_rows),
             '<p class="muted">Tanpa kunci, field AEAD tidak berhasil dipulihkan pada skenario yang diuji. Kebocoran kapabilitas PII/FIN/search meningkatkan paparan sesuai domain; search memungkinkan serangan kamus pada nilai sintetis yang diketahui. Kolom REF, pola NULL, panjang dan equality tetap dapat terlihat.</p>',
             '<h3>Ukuran dan waktu backup/restore</h3><p>Uji operasional ' + str(data['backup']['source_rows']) + ' record: backup terenkripsi <strong>' + number(data['backup']['backup_seconds']) + ' detik</strong>, restore <strong>' + number(data['restore']['restore_seconds']) + ' detik</strong>, artefak <strong>' + number(data['backup']['size_bytes']/1048576) + ' MiB</strong>. Ini satu pengujian operasional, bukan median benchmark tiga run. <a href="../evidence/backup/restore-report.json">Hasil restore</a>.</p>',
             '<h3>Ketepatan assessment</h3><p>Precision ' + number(scanner['precision']*100) + '%, recall ' + number(scanner['recall']*100) + '%, F1 ' + number(scanner['f1']*100) + '%. Evaluasi in-sample terhadap 29 kolom; bukan jaminan akurasi pada semua database.</p></section>',
             '<section id="service"><h2>Aplikasi dan enam akun</h2><p><a href="https://43.156.157.247/login">Buka aplikasi HTTPS yang dideploy</a> · <a href="../accounts.md">Akun evaluator</a></p><p>Halaman login terakhir diperiksa: ' + escape(deployed['checked_at_utc']) + '; HTTP ' + str(deployed.get('http_status','tidak tersedia')) + ', TLS ' + ('terverifikasi' if deployed.get('tls_verified') else 'belum terverifikasi') + '. Ini pemeriksaan halaman login, bukan pengujian ulang seluruh role VM.</p>',
             deployment_status,
             '<p>Acceptance lokal memakai PostgreSQL 18/OpenBao nyata dengan TLS serta Chrome, termasuk aplikasi di atas database hasil restore. Pemeriksaan browser pada run lulus terakhir: <strong>' + str(browser_count) + '</strong>. Uji deployment dan uji lab mempunyai lingkungan berbeda.</p>', table(('Run', 'Hasil', 'Lingkungan', 'Check browser'), run_rows),
             '<p>Peran evaluator: operator (identitas dimasking), privileged officer (PII sesuai scope), finance officer (FIN sesuai scope), anggota (record sendiri), analyst (agregat), auditor (metadata audit). <a href="ACCESS_CONTROL.md">Rincian izin</a>.</p></section>',
             '<section id="performance"><span class="tag warn">TARGET LATENSI / THROUGHPUT BELUM TERCAPAI</span><h2>Harga kinerja perlindungan</h2><p>Perbandingan DB B-P-P-B pada perangkat dan populasi yang sama, empat pengukuran per mode/skenario; tabel menggunakan median antarrun. Angka ini level DB/toolkit, bukan waktu respons web publik.</p>', chart,
             '<p>p95 berarti 95% permintaan selesai dalam waktu tersebut atau lebih cepat; makin kecil makin baik. Throughput adalah permintaan per detik; makin besar makin baik. Seluruh 14 kombinasi skala/skenario belum memenuhi P01/P01A/P02; error-rate P03 lulus. Optimasi menurunkan overhead tetapi belum menutup selisih tersebut.</p>',
             '<h3>Biaya penyimpanan</h3><p>Snapshot ukuran database setelah migrasi; termasuk overhead tabel/index/kontrol pada snapshot tersebut, bukan konstanta overhead setiap record.</p>', table(('Skala', 'Baseline (MiB)', 'Terproteksi (MiB)', 'Rasio'), storage_rows),
             '<details><summary>Seluruh hasil DB v2 — p50/p95 (ms) dan throughput (req/s)</summary>', table(('Skala','Skenario','p50 awal','p50 terproteksi','p95 awal','p95 terproteksi','RPS awal','RPS terproteksi'), benchmark_rows), '</details>',
             '<details><summary>CPU dan RAM pada mode terproteksi</summary><p>CPU memakai persentase satu core sehingga dapat melebihi 100%. RAM adalah peak antarrun; bukan ukuran minimum instalasi.</p>', table(('Skala','Skenario','CPU klien median','RAM klien peak','CPU DB median','RAM DB peak','RAM Bao peak'), resource_rows), '</details>',
             '<p>Hasil naive, v2, raw, resource, dan target tetap disimpan. Seri benchmark API belum lengkap; tidak diperlakukan sebagai hasil DB. Lihat <a href="METHODOLOGY.md">metodologi</a> dan <a href="data/db-benchmark.csv">tabel lengkap</a>.</p></section>',
             '<section id="limits"><h2>Kesimpulan dan keterbatasan</h2><p>Pelindungan field, pembatasan akses, keberlangsungan layanan dan restore sudah mempunyai bukti berjalan pada scope yang disebut. Hasil kinerja belum memenuhi target. Sistem ini belum menjadi bukti bahwa seluruh storage, log, aplikasi dan key plane kebal kompromi.</p><ul><li>Kompromi aplikasi sekaligus kemampuan decrypt dapat membuka data sesuai kapabilitas yang dicuri.</li><li>Blind index mengungkap kesetaraan/frekuensi; REF dan NULL masih terlihat. Populasi sumber 734 masih memiliki proyeksi residual k=1. Suppression analis bukan differential privacy.</li><li>RLS berbasis setting transaksi bisa dimanipulasi pencuri credential app_user.</li><li>Backup lama dapat tetap berisi record yang kemudian dihapus sampai retensi berakhir.</li><li>DR seluruh key plane, HA, secure erase, dan audit seluruh riwayat/log host belum dibuktikan lengkap.</li><li>S02 historis pada salinan API memiliki kegagalan analis. Acceptance baru tidak mengganti label hasil pada lingkungan yang berbeda.</li></ul><p><a href="SECURITY.md">Model ancaman dan batas keamanan</a> · <a href="OPERATIONS.md">Operasi dan pemulihan</a>.</p></section>',
             '<footer>Angka berasal dari hasil yang tersimpan, tanpa menjalankan benchmark baru. JSON/CSV menyimpan detail yang dapat diperiksa mesin; halaman ini adalah penjelasannya. <a href="../evidence/benchmark/bppb_v2_100k/summary.json">Sumber DB 100k</a> · <a href="../evidence/benchmark/bppb_v2_1m/summary.json">Sumber DB 1M</a> · <a href="../evidence/scanner/evaluation_v1_2.json">Sumber scanner</a> · <a href="data/leakage.csv">Paparan data</a>.</footer></main></body></html>']
    return ''.join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/RESULTS.html')
    args = parser.parse_args(argv)
    data = load(ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(data), encoding='utf-8')
    print('Hasil dapat dibaca di: ' + str(args.output))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
