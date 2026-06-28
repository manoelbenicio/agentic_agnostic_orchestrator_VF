/* =============================================
   DSS Showcase — JavaScript v3.0
   Tech Stack: Canvas 2D Geodesic Sphere + IntersectionObserver
   Scroll Reveals + Custom Cursor + KPI Counter Animation
   All colors: Official Indra Corporate Palette
   ============================================= */

// === CUSTOM CURSOR ===
const cursorDot = document.getElementById('cursorDot');
const cursorRing = document.getElementById('cursorRing');
let mouseX = 0, mouseY = 0, ringX = 0, ringY = 0;

document.addEventListener('mousemove', (e) => {
  mouseX = e.clientX; mouseY = e.clientY;
  cursorDot.style.left = mouseX + 'px';
  cursorDot.style.top = mouseY + 'px';
});

function animateCursorRing() {
  ringX += (mouseX - ringX) * 0.15;
  ringY += (mouseY - ringY) * 0.15;
  cursorRing.style.left = ringX + 'px';
  cursorRing.style.top = ringY + 'px';
  requestAnimationFrame(animateCursorRing);
}
animateCursorRing();

document.querySelectorAll('a, button, .btn, .card, .glass-card, .color-swatch').forEach(el => {
  el.addEventListener('mouseenter', () => cursorRing.classList.add('hover'));
  el.addEventListener('mouseleave', () => cursorRing.classList.remove('hover'));
});

// === SCROLL REVEAL ===
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('animate-in');
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.12 });

document.querySelectorAll('[data-animate]').forEach(el => revealObserver.observe(el));

// === KPI COUNTER ===
function animateCounter(element, target, suffix = '') {
  const start = performance.now();
  const duration = 1500;
  function update(now) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.round(target * eased);
    element.textContent = current.toLocaleString() + suffix;
    if (progress < 1) requestAnimationFrame(update);
  }
  requestAnimationFrame(update);
}

const kpiObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const el = entry.target;
      const target = parseInt(el.dataset.count);
      const suffix = el.dataset.suffix || '';
      animateCounter(el, target, suffix);
      kpiObserver.unobserve(el);
    }
  });
}, { threshold: 0.5 });

document.querySelectorAll('[data-count]').forEach(el => kpiObserver.observe(el));

// === THEME TOGGLE ===
const themeToggle = document.getElementById('themeToggle');
themeToggle.addEventListener('click', () => {
  const html = document.documentElement;
  const current = html.getAttribute('data-theme');
  html.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
});

// === GEODESIC SPHERE (Canvas 2D) ===
const canvas = document.getElementById('heroCanvas');
const ctx = canvas.getContext('2d');

function resizeCanvas() {
  canvas.width = canvas.parentElement.offsetWidth;
  canvas.height = canvas.parentElement.offsetHeight;
}
resizeCanvas();
window.addEventListener('resize', resizeCanvas);

// Icosahedron base vertices
const phi = (1 + Math.sqrt(5)) / 2;
const icoVertices = [
  [-1, phi, 0], [1, phi, 0], [-1, -phi, 0], [1, -phi, 0],
  [0, -1, phi], [0, 1, phi], [0, -1, -phi], [0, 1, -phi],
  [phi, 0, -1], [phi, 0, 1], [-phi, 0, -1], [-phi, 0, 1]
].map(v => { const l = Math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]); return [v[0]/l, v[1]/l, v[2]/l]; });

const icoFaces = [
  [0,11,5],[0,5,1],[0,1,7],[0,7,10],[0,10,11],
  [1,5,9],[5,11,4],[11,10,2],[10,7,6],[7,1,8],
  [3,9,4],[3,4,2],[3,2,6],[3,6,8],[3,8,9],
  [4,9,5],[2,4,11],[6,2,10],[8,6,7],[9,8,1]
];

// Subdivide
function midpoint(a, b) {
  const m = [(a[0]+b[0])/2, (a[1]+b[1])/2, (a[2]+b[2])/2];
  const l = Math.sqrt(m[0]*m[0]+m[1]*m[1]+m[2]*m[2]);
  return [m[0]/l, m[1]/l, m[2]/l];
}

let vertices = [...icoVertices];
let faces = [...icoFaces];
const midCache = {};

function getMidIndex(i1, i2) {
  const key = Math.min(i1,i2)+'-'+Math.max(i1,i2);
  if (midCache[key] !== undefined) return midCache[key];
  const mid = midpoint(vertices[i1], vertices[i2]);
  vertices.push(mid);
  midCache[key] = vertices.length - 1;
  return midCache[key];
}

for (let s = 0; s < 2; s++) {
  const newFaces = [];
  for (const [a,b,c] of faces) {
    const ab = getMidIndex(a,b);
    const bc = getMidIndex(b,c);
    const ca = getMidIndex(c,a);
    newFaces.push([a,ab,ca],[b,bc,ab],[c,ca,bc],[ab,bc,ca]);
  }
  faces = newFaces;
}

// Extract edges
const edgeSet = new Set();
const edges = [];
for (const [a,b,c] of faces) {
  [[a,b],[b,c],[c,a]].forEach(([i,j]) => {
    const key = Math.min(i,j)+'-'+Math.max(i,j);
    if (!edgeSet.has(key)) { edgeSet.add(key); edges.push([i,j]); }
  });
}

// Pulse particles
const particles = [];
for (let i = 0; i < 8; i++) {
  particles.push({
    edge: Math.floor(Math.random() * edges.length),
    t: Math.random(),
    speed: 0.002 + Math.random() * 0.003,
    size: 1.5 + Math.random() * 2
  });
}

let rotX = 0, rotY = 0;
let parallaxX = 0, parallaxY = 0;

document.addEventListener('mousemove', (e) => {
  parallaxX = (e.clientX / window.innerWidth - 0.5) * 0.02;
  parallaxY = (e.clientY / window.innerHeight - 0.5) * 0.02;
});

function project(v) {
  // Rotate Y
  let x = v[0]*Math.cos(rotY) + v[2]*Math.sin(rotY);
  let z = -v[0]*Math.sin(rotY) + v[2]*Math.cos(rotY);
  let y = v[1];
  // Rotate X
  const ny = y*Math.cos(rotX) - z*Math.sin(rotX);
  const nz = y*Math.sin(rotX) + z*Math.cos(rotX);
  y = ny; z = nz;
  // Parallax
  x += parallaxX; y += parallaxY;
  // Perspective
  const scale = Math.min(canvas.width, canvas.height) * 0.28;
  const perspective = 4 / (4 + z);
  return [
    canvas.width / 2 + x * scale * perspective,
    canvas.height / 2 - y * scale * perspective,
    z
  ];
}

function render() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  rotY += 0.001;
  rotX += 0.0003;

  // Draw edges
  for (const [i, j] of edges) {
    const [x1, y1, z1] = project(vertices[i]);
    const [x2, y2, z2] = project(vertices[j]);
    const avgZ = (z1 + z2) / 2;
    const alpha = 0.08 + (1 + avgZ) * 0.12;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.strokeStyle = `rgba(0, 176, 189, ${Math.max(0.03, alpha)})`;
    ctx.lineWidth = 0.6;
    ctx.stroke();
  }

  // Draw vertices
  for (const v of vertices) {
    const [x, y, z] = project(v);
    const alpha = 0.1 + (1 + z) * 0.2;
    const size = 1 + (1 + z) * 0.5;
    ctx.beginPath();
    ctx.arc(x, y, size, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(63, 150, 174, ${Math.max(0.05, alpha)})`;
    ctx.fill();
  }

  // Draw particles
  for (const p of particles) {
    p.t += p.speed;
    if (p.t > 1) { p.t = 0; p.edge = Math.floor(Math.random() * edges.length); }
    const [i, j] = edges[p.edge];
    const v = [
      vertices[i][0] + (vertices[j][0] - vertices[i][0]) * p.t,
      vertices[i][1] + (vertices[j][1] - vertices[i][1]) * p.t,
      vertices[i][2] + (vertices[j][2] - vertices[i][2]) * p.t,
    ];
    const [x, y] = project(v);
    ctx.beginPath();
    ctx.arc(x, y, p.size, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(186, 223, 243, 0.7)`;
    ctx.fill();
  }

  requestAnimationFrame(render);
}
render();

// === CONTACT FORM ===
document.getElementById('contactForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const btn = e.target.querySelector('.btn--form');
  btn.textContent = '✓ Sent Successfully';
  btn.style.background = '#27AE60';
  setTimeout(() => { btn.textContent = 'Send Message'; btn.style.background = ''; }, 2000);
});
