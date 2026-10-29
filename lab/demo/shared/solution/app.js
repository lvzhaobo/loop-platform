// 番茄时钟 —— 支持自定义时长（25 / 5 为默认）
const DEFAULT_WORK = 25;
const DEFAULT_BREAK = 5;
const MIN_MINUTES = 1;
const MAX_MINUTES = 180;
const CIRCUMFERENCE = 603;

const $timer = document.getElementById('timer');
const $mode = document.getElementById('mode');
const $toggle = document.getElementById('toggle');
const $reset = document.getElementById('reset');
const $progress = document.getElementById('progress');
const $hint = document.getElementById('hint');
const $card = document.querySelector('.card');
const $work = document.getElementById('work-minutes');
const $break = document.getElementById('break-minutes');

let mode = 'work';
let total = DEFAULT_WORK * 60;
let remaining = total;
let running = false;
let ticker = null;

// 非法值（NaN / <=0 / >180）一律回退到默认值
function clampMinutes(raw, fallback) {
  const v = Number(raw);
  if (!Number.isFinite(v) || v <= 0 || v > MAX_MINUTES) return fallback;
  return Math.floor(v);
}

function readDurations() {
  return {
    work: clampMinutes($work && $work.value, DEFAULT_WORK) * 60,
    break: clampMinutes($break && $break.value, DEFAULT_BREAK) * 60,
  };
}

function fmt(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
}

function render() {
  $timer.textContent = fmt(remaining);
  $mode.textContent = mode === 'work' ? '专注' : '休息';
  $card.classList.toggle('break', mode === 'break');
  const ratio = total ? remaining / total : 0;
  $progress.style.strokeDashoffset = String(CIRCUMFERENCE * (1 - ratio));
}

function applyDurations() {
  const d = readDurations();
  total = mode === 'work' ? d.work : d.break;
  remaining = total;
  render();
}

function switchMode() {
  mode = mode === 'work' ? 'break' : 'work';
  const d = readDurations();
  total = mode === 'work' ? d.work : d.break;
  remaining = total;
  render();
}

function tick() {
  remaining -= 1;
  if (remaining <= 0) {
    $hint.textContent = mode === 'work' ? '专注结束，休息一下' : '休息结束，继续专注';
    switchMode();
    return;
  }
  render();
}

function start() {
  if (running) return;
  running = true;
  $toggle.textContent = '暂停';
  ticker = setInterval(tick, 1000);
}

function pause() {
  running = false;
  $toggle.textContent = '开始';
  clearInterval(ticker);
}

$toggle.addEventListener('click', () => (running ? pause() : start()));

$reset.addEventListener('click', () => {
  pause();
  mode = 'work';
  applyDurations();
  $hint.textContent = '';
});

$work.addEventListener('change', () => { if (!running) applyDurations(); });
$break.addEventListener('change', () => { if (!running) applyDurations(); });

render();
