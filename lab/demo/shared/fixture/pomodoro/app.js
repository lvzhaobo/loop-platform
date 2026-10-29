// 番茄时钟 —— 25 分钟专注 / 5 分钟休息
// TODO（这是任务要改的部分）：时长目前写死，需要支持自定义

const WORK_SECONDS = 25 * 60;
const BREAK_SECONDS = 5 * 60;
const CIRCUMFERENCE = 603;

let remaining = WORK_SECONDS;
let total = WORK_SECONDS;
let running = false;
let mode = 'work';
let ticker = null;

const $timer = document.getElementById('timer');
const $mode = document.getElementById('mode');
const $toggle = document.getElementById('toggle');
const $reset = document.getElementById('reset');
const $progress = document.getElementById('progress');
const $hint = document.getElementById('hint');
const $card = document.querySelector('.card');

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

function switchMode() {
  mode = mode === 'work' ? 'break' : 'work';
  total = mode === 'work' ? WORK_SECONDS : BREAK_SECONDS;
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
  total = WORK_SECONDS;
  remaining = total;
  $hint.textContent = '';
  render();
});

render();
