//#region src/knowledge-map/geometry.ts
var e = Math.PI * 2;
function t(e) {
	let t = Math.hypot(...e);
	return t < 1e-10 ? [
		0,
		0,
		1
	] : e.map((e) => e / t);
}
function n([e, t, n], r) {
	let i = Math.cos(r.yaw) * e + Math.sin(r.yaw) * n, a = -Math.sin(r.yaw) * e + Math.cos(r.yaw) * n;
	return [
		i,
		Math.cos(r.pitch) * t - Math.sin(r.pitch) * a,
		Math.sin(r.pitch) * t + Math.cos(r.pitch) * a
	];
}
function r([e, t, n], r) {
	let i = -Math.sin(r.pitch) * t + Math.cos(r.pitch) * n;
	return [
		Math.cos(r.yaw) * e - Math.sin(r.yaw) * i,
		Math.cos(r.pitch) * t + Math.sin(r.pitch) * n,
		Math.sin(r.yaw) * e + Math.cos(r.yaw) * i
	];
}
function i(e, t) {
	return {
		...t,
		yaw: -Math.atan2(e[0], e[2]),
		pitch: Math.atan2(e[1], Math.hypot(e[0], e[2]))
	};
}
function a(e, t, r, i, a = !1) {
	let o = Math.min(r, i) * .38 * t.zoom;
	if (a) return {
		x: r / 2 + Math.atan2(e[0], e[2]) / Math.PI * o,
		y: i / 2 - Math.asin(e[1]) / (Math.PI / 2) * o,
		z: 1
	};
	let [s, c, l] = n(e, t);
	return {
		x: r / 2 + s * o,
		y: i / 2 - c * o,
		z: l
	};
}
function o(e, n, i, a, o) {
	let s = Math.min(a, o) * .38 * i.zoom, c = (e - a / 2) / s, l = -(n - o / 2) / s;
	return t(r(t([
		c,
		l,
		Math.sqrt(Math.max(0, 1 - c * c - l * l))
	]), i));
}
function s(e, n, r) {
	let i = { ...n }, a = [...e].sort(), o = Object.keys(n).length > 0;
	return a.forEach((e, n) => {
		if (i[e]) return;
		let s = 1 - 2 * (n + .5) / a.length, c = n * Math.PI * (3 - Math.sqrt(5)), l = t([
			Math.cos(c) * Math.sqrt(1 - s * s),
			s,
			Math.sin(c) * Math.sqrt(1 - s * s)
		]);
		r?.key === e && (l = t(r.point));
		let u = o || r?.key === e ? Object.values(i) : [];
		for (let e = 0; e < 48 && u.some((e) => Math.hypot(e[0] - l[0], e[1] - l[1], e[2] - l[2]) < .09); e++) l = t([
			l[0] + .11 * Math.cos(e * 2.4),
			l[1] + .11 * Math.sin(e * 2.4),
			l[2]
		]);
		i[e] = l;
	}), i;
}
function c(n, r, i = 0, a = !1) {
	let o = Math.max(-1, Math.min(1, n.reduce((e, t, n) => e + t * r[n], 0))), s = Math.abs(n[1]) < .8 ? [
		0,
		1,
		0
	] : [
		1,
		0,
		0
	], c = t([
		n[1] * s[2] - n[2] * s[1],
		n[2] * s[0] - n[0] * s[2],
		n[0] * s[1] - n[1] * s[0]
	]);
	if (a || o > .99999) return Array.from({ length: 33 }, (r, a) => {
		let o = a / 32 * e, l = .1 + Math.abs(i) * .04;
		return t(n.map((e, t) => e + c[t] * Math.sin(o) * l + s[t] * (1 - Math.cos(o)) * l));
	});
	let l = Math.acos(o), u = Math.sin(l);
	return Array.from({ length: 25 }, (e, a) => {
		let o = a / 24;
		return t((u < 1e-4 ? n.map((e, t) => Math.cos(Math.PI * o) * e + Math.sin(Math.PI * o) * c[t]) : n.map((e, t) => (Math.sin((1 - o) * l) * e + Math.sin(o * l) * r[t]) / u)).map((e, t) => e + i * .035 * Math.sin(Math.PI * o) * c[t]));
	});
}
//#endregion
//#region src/knowledge-map/model.ts
function l() {
	return {
		camera: {
			yaw: 0,
			pitch: 0,
			zoom: 1
		},
		flat: !1,
		selected: "",
		source: "",
		type: "",
		relation: "",
		points: {},
		auto: !1
	};
}
function u(e, t) {
	return e.nodes.filter((e) => (!t.source || e.source === t.source) && (!t.type || e.tipo === t.type));
}
function d(e, t, n) {
	let r = new Set(t.map((e) => e.key));
	return e.edges.filter((e) => r.has(e.from) && r.has(e.to) && (!n.relation || e.tipo === n.relation));
}
function f(e, t) {
	let n = /* @__PURE__ */ new Set();
	return e.edges.forEach((e) => {
		e.from === t && n.add(e.to), e.to === t && n.add(e.from);
	}), e.nodes.filter((e) => n.has(e.key));
}
function p(e, t, n, r) {
	let i = e.nodes.find((e) => e.key === t.selected);
	return {
		action: n,
		title: n === "edit" ? i?.titulo ?? "" : "",
		content: n === "edit" ? i?.contenido_latex ?? "" : "",
		comment: n === "edit" ? i?.comentario ?? "" : "",
		categories: n === "edit" ? i?.categorias.join(", ") ?? "" : "",
		source: e.sources[0]?.id ?? "",
		type: "nota",
		origin: i?.key ?? "",
		target: "",
		relation: "requiere_concepto",
		reverse: !1,
		revision: i?.revision ?? "",
		point: r
	};
}
function m(e, t) {
	return e.action === "connect" ? {
		operation_id: t,
		action: "connect",
		key: e.origin,
		target: e.target,
		relation_type: e.relation,
		reverse: e.reverse
	} : {
		operation_id: t,
		action: e.action,
		key: e.origin,
		source_id: e.source,
		titulo: e.title,
		tipo: e.type,
		contenido_latex: e.content,
		comentario: e.comment,
		categorias: e.categories.split(",").map((e) => e.trim()).filter(Boolean),
		revision: e.revision,
		relation_type: e.relation,
		reverse: e.reverse
	};
}
function h(e, t) {
	let n = e.result;
	!n || n.operation_id !== t.pending?.operation_id || (t.status = n, n.status === "saved" || n.status === "duplicate" ? (n.key && (t.selected = n.key), t.acknowledged = n.operation_id, t.pending = void 0, t.draft = void 0) : (n.status === "conflict" || n.status === "invalid") && (t.pending = void 0));
}
//#endregion
//#region src/knowledge-map/canvas.ts
var g = {
	definicion: "#65e5ce",
	teorema: "#ffe29a",
	proposicion: "#7abfff",
	corolario: "#d0b4ff",
	lema: "#ffa3b5",
	ejemplo: "#ffbd72",
	nota: "#bfccd9"
}, _ = class {
	canvas;
	data;
	view;
	select;
	create;
	changed;
	context;
	width = 600;
	height = 470;
	frame = 0;
	lastTime = 0;
	shown = !0;
	stopped = !1;
	hover = "";
	drag;
	nodes = [];
	paths = [];
	projected = /* @__PURE__ */ new Map();
	controller = new AbortController();
	resize;
	intersection;
	motion = window.matchMedia("(prefers-reduced-motion: reduce)");
	constructor(e, t, n, r, i, a) {
		this.canvas = e, this.data = t, this.view = n, this.select = r, this.create = i, this.changed = a;
		let s = e.getContext("2d");
		if (!s) throw Error("Canvas no disponible; usa los formularios accesibles.");
		this.context = s;
		let c = { signal: this.controller.signal };
		e.addEventListener("pointerdown", (t) => {
			this.pause(), this.drag = {
				x: t.clientX,
				y: t.clientY,
				moved: !1
			}, e.setPointerCapture(t.pointerId);
		}, c), e.addEventListener("pointermove", (e) => this.move(e), c), e.addEventListener("pointerup", (e) => this.up(e), c), e.addEventListener("pointercancel", () => {
			this.drag = void 0;
		}, c), e.addEventListener("pointerleave", () => {
			this.hover = "", this.request();
		}, c), e.addEventListener("contextmenu", (t) => {
			t.preventDefault(), this.pause();
			let r = e.getBoundingClientRect();
			this.create(o(t.clientX - r.left, t.clientY - r.top, n.camera, this.width, this.height));
		}, c), e.addEventListener("keydown", (e) => this.keyboard(e), c), document.addEventListener("visibilitychange", () => this.request(), c), this.motion.addEventListener("change", () => {
			this.pause(), this.request();
		}, c), this.resize = new ResizeObserver((t) => {
			this.width = Math.max(200, t[0].contentRect.width);
			let n = Math.min(window.devicePixelRatio || 1, 2);
			e.width = this.width * n, e.height = this.height * n, this.context.setTransform(n, 0, 0, n, 0, 0), this.request();
		}), this.resize.observe(e), this.intersection = new IntersectionObserver((e) => {
			this.shown = e[0].isIntersecting, this.request();
		}), this.intersection.observe(e), this.update(t);
	}
	update(e) {
		this.data = e, this.nodes = u(e, this.view);
		let t = /* @__PURE__ */ new Map();
		this.paths = d(e, this.nodes, this.view).map((e) => {
			let n = [e.from, e.to].sort().join("\0"), r = t.get(n) ?? 0;
			return t.set(n, r + 1), {
				from: e.from,
				to: e.to,
				points: c(this.view.points[e.from], this.view.points[e.to], r, e.from === e.to)
			};
		}), this.canvas.dataset.nodes = String(this.nodes.length), this.canvas.dataset.edges = String(this.paths.length), this.request();
	}
	pause() {
		this.view.auto = !1;
	}
	request() {
		!this.frame && !this.stopped && (this.frame = requestAnimationFrame((e) => this.draw(e)));
	}
	move(e) {
		if (this.drag) {
			let t = e.clientX - this.drag.x, n = e.clientY - this.drag.y;
			Math.abs(t) + Math.abs(n) > 2 && (this.drag.moved = !0), this.view.camera.yaw += t * .007, this.view.camera.pitch += n * .007, this.drag.x = e.clientX, this.drag.y = e.clientY, this.changed();
		} else {
			let t = this.canvas.getBoundingClientRect();
			this.hover = this.hit(e.clientX - t.left, e.clientY - t.top);
		}
		this.request();
	}
	up(e) {
		let t = this.drag?.moved;
		if (this.drag = void 0, this.canvas.releasePointerCapture(e.pointerId), !t) {
			let t = this.canvas.getBoundingClientRect(), n = this.hit(e.clientX - t.left, e.clientY - t.top);
			n && this.select(n);
		}
		this.changed();
	}
	hit(e, t) {
		let n = "", r = -2;
		return this.projected.forEach((i, a) => {
			Math.hypot(i.x - e, i.y - t) < 15 && i.z > r && (n = a, r = i.z);
		}), n;
	}
	keyboard(e) {
		let t = {
			ArrowLeft: [-.12, 0],
			ArrowRight: [.12, 0],
			ArrowUp: [0, -.12],
			ArrowDown: [0, .12]
		};
		t[e.key] && (e.preventDefault(), this.pause(), this.view.camera.yaw += t[e.key][0], this.view.camera.pitch += t[e.key][1], this.changed(), this.request());
	}
	bringFront(e) {
		this.pause(), this.view.camera = i(this.view.points[e], this.view.camera), this.request();
	}
	draw(e) {
		if (this.frame = 0, this.stopped || document.hidden || !this.shown) {
			this.lastTime = 0;
			return;
		}
		let t = performance.now(), n = this.context, r = this.view.camera, i = this.view.auto && !this.view.draft && !this.view.selected && !this.motion.matches && !this.view.flat;
		i && this.lastTime && (r.yaw += Math.min(e - this.lastTime, 50) * 45e-6), this.lastTime = e, n.clearRect(0, 0, this.width, this.height);
		let o = Math.min(this.width, this.height) * .38 * r.zoom;
		if (n.strokeStyle = "#26485c", n.lineWidth = 1, this.view.flat || (n.beginPath(), n.arc(this.width / 2, this.height / 2, o, 0, Math.PI * 2), n.stroke()), this.drawEdges(n), this.projected.clear(), this.nodes.map((e) => ({
			node: e,
			point: a(this.view.points[e.key], r, this.width, this.height, this.view.flat)
		})).sort((e, t) => e.point.z - t.point.z).forEach(({ node: e, point: t }) => this.drawNode(n, e, t)), this.drawProposal(n), this.view.draft && this.view.draft.action.startsWith("create")) {
			let e = a(this.view.draft.point, r, this.width, this.height, this.view.flat);
			n.globalAlpha = .9, n.strokeStyle = "#ffffff", n.setLineDash([4, 4]), n.beginPath(), n.arc(e.x, e.y, 12, 0, Math.PI * 2), n.stroke(), n.setLineDash([]), n.fillStyle = "#ffffff", n.fillText("Borrador", e.x + 16, e.y);
		}
		n.globalAlpha = 1, this.canvas.dataset.renderMs = String(performance.now() - t), i && this.request();
	}
	drawProposal(e) {
		let t = this.view.draft;
		if (!t || !["connect", "create_connected"].includes(t.action)) return;
		let n = this.view.points[t.origin], r = t.action === "connect" ? this.view.points[t.target] : t.point;
		!n || !r || (e.globalAlpha = .85, e.strokeStyle = "#f5dc9b", e.lineWidth = 2, e.setLineDash([5, 5]), e.beginPath(), c(n, r).forEach((t, n) => {
			let r = a(t, this.view.camera, this.width, this.height, this.view.flat);
			n === 0 ? e.moveTo(r.x, r.y) : e.lineTo(r.x, r.y);
		}), e.stroke(), e.setLineDash([]));
	}
	drawEdges(e) {
		let t = this.paths.map((e) => ({
			strong: [this.hover, this.view.selected].some((t) => !!t && (e.from === t || e.to === t)),
			points: e.points.map((e) => a(e, this.view.camera, this.width, this.height, this.view.flat))
		}));
		for (let n of [!1, !0]) for (let r of [!0, !1]) e.lineWidth = n ? 1.8 : .8, e.strokeStyle = n ? "#71f6e0" : "#4b8194", e.globalAlpha = r ? .12 : n ? .9 : .45, e.beginPath(), t.filter((e) => e.strong === n).forEach((t) => {
			for (let n = 1; n < t.points.length; n++) {
				let i = t.points[n - 1], a = t.points[n];
				a.z < 0 !== r || this.view.flat && Math.abs(i.x - a.x) > this.width * .35 || (e.moveTo(i.x, i.y), e.lineTo(a.x, a.y));
			}
			let n = t.points[t.points.length - 3], i = t.points[t.points.length - 4];
			if (n.z < 0 === r) {
				let t = Math.atan2(n.y - i.y, n.x - i.x);
				e.moveTo(n.x - 6 * Math.cos(t - .5), n.y - 6 * Math.sin(t - .5)), e.lineTo(n.x, n.y), e.lineTo(n.x - 6 * Math.cos(t + .5), n.y - 6 * Math.sin(t + .5));
			}
		}), e.stroke();
	}
	drawNode(e, t, n) {
		this.projected.set(t.key, n);
		let r = t.key === this.view.selected, i = r || t.key === this.hover;
		if (e.globalAlpha = n.z < 0 ? .25 : .6 + .4 * n.z, e.fillStyle = g[t.tipo] ?? "#bfccd9", e.beginPath(), e.arc(n.x, n.y, i ? 7 : 3 + (n.z + 1), 0, Math.PI * 2), e.fill(), r && (e.strokeStyle = "#ffffff", e.lineWidth = 2, e.beginPath(), e.arc(n.x, n.y, 11, 0, Math.PI * 2), e.stroke()), i || this.nodes.length < 35 && n.z > .1) {
			e.fillStyle = "#edf9ff", e.font = i ? "bold 13px system-ui" : "12px system-ui";
			let r = t.titulo.length > 37 ? t.titulo.slice(0, 35) + "…" : t.titulo;
			e.fillText(r, Math.max(4, Math.min(n.x + 13, this.width - e.measureText(r).width - 4)), n.y - 9);
		}
	}
	destroy() {
		this.stopped = !0, cancelAnimationFrame(this.frame), this.frame = 0, this.controller.abort(), this.resize.disconnect(), this.intersection.disconnect();
	}
}, v = /* @__PURE__ */ new Map(), y = /* @__PURE__ */ new WeakMap();
function b(e, t = "", n = "") {
	let r = document.createElement(e);
	return r.textContent = t, r.className = n, r;
}
function x(e, t, n, r = !1) {
	let i = b("button", e, r ? "primary" : "");
	return i.type = "button", i.onclick = t, n.append(i), i;
}
function S(e, t, n, r, i = !1) {
	let a = b("label", t), o = b(i ? "textarea" : "input");
	return o.setAttribute("aria-label", t), o.value = n, o.oninput = () => r(o.value), a.append(o), e.append(a), o;
}
function C(e, t, n, r, i) {
	let a = b("label", t), o = b("select");
	return n.forEach((e) => {
		let t = b("option", e.text);
		t.value = e.value, o.append(t);
	}), o.setAttribute("aria-label", t), o.value = r, o.onchange = () => i(o.value), a.append(o), e.append(a), o;
}
function w(e) {
	if (v.has(e)) return v.get(e);
	try {
		let t = JSON.parse(sessionStorage.getItem("mathmongo-map-" + e) ?? "null");
		if (t && t.camera && [
			"yaw",
			"pitch",
			"zoom"
		].every((e) => Number.isFinite(t.camera[e])) && t.points) return t;
	} catch {}
	return l();
}
function T(e) {
	let { parentElement: t, data: n, setTriggerValue: i } = e;
	y.get(t)?.();
	let a = w(n.scope);
	v.set(n.scope, a);
	let o = a.pending && n.result?.key && a.draft ? {
		key: n.result.key,
		point: a.draft.point
	} : void 0;
	a.points = s(n.nodes.map((e) => e.key), a.points, o), h(n, a), a.pending && n.result?.operation_id !== a.pending.operation_id && (a.status = {
		status: "uncertain",
		message: "Existe un envío anterior sin confirmar. Reconcilia el mismo intento antes de continuar."
	});
	let c = () => {
		try {
			sessionStorage.setItem("mathmongo-map-" + n.scope, JSON.stringify(a));
		} catch {}
	}, l = b("section", "", "knowledge-map");
	l.setAttribute("aria-label", "Mapa de conocimiento editable");
	let d = b("div", "Una idea abre un camino", "eyebrow");
	l.append(d, b("h2", "Tu conocimiento, conectado"));
	let T = b("div", "", "toolbar"), E = b("div", "", "layout"), D = b("div", "", "stage"), O = b("aside"), k = b("canvas");
	k.tabIndex = 0, k.setAttribute("role", "img"), k.setAttribute("aria-label", "Superficie del conocimiento. Flechas para girar; usa el selector para elegir conceptos.");
	let A = b("div", "", "status");
	A.setAttribute("role", "status"), A.setAttribute("aria-live", "polite");
	let j = b("div", "", "filters");
	l.append(T, j, A, E), E.append(D, O), D.append(k), D.append(b("p", "Arrastra para girar · flechas con el mapa enfocado · clic derecho para crear aquí", "hint"));
	let M = b("div", "", "legend");
	Object.entries(g).forEach(([e, t]) => {
		let n = b("span", e);
		n.style.setProperty("--node-color", t), M.append(n);
	}), D.append(M), (t.querySelector(".knowledge-map-root") ?? t).replaceChildren(l);
	let N, P = new _(k, n, a, (e) => I(e), (e) => L("create", e), () => {
		c(), q && (q.textContent = a.auto ? "Pausar giro" : "Giro suave");
	}), F = () => {
		P.update(n), c();
	}, I = (e) => {
		if (a.draft) {
			a.status = {
				status: "draft",
				message: "Conserva o cancela el borrador antes de cambiar la selección."
			}, V();
			return;
		}
		a.selected = e, X.value = e, P.bringFront(e), U(), F(), V();
	}, L = (e, t = r([
		0,
		0,
		1
	], a.camera)) => {
		if (a.pending || a.draft) return;
		P.pause();
		let i = s([...n.nodes.map((e) => e.key), "__draft__"], a.points, {
			key: "__draft__",
			point: t
		}).__draft__;
		a.draft = p(n, a, e, i), a.status = {
			status: "draft",
			message: "Borrador: aún no se ha escrito en la base."
		}, U(), V(), F();
	}, R = () => {
		U(), V(), F();
	}, z = () => {
		!a.draft || a.pending || (a.draft.submitted = !0, a.pending = m(a.draft, crypto.randomUUID()), B());
	}, B = () => {
		a.pending && (a.status = {
			status: "saving",
			message: "Guardando… espera la confirmación. El envío ya no se puede cancelar."
		}, c(), V(), U(), i("intent", a.pending), N = setTimeout(() => {
			a.status = {
				status: "uncertain",
				message: "La confirmación tarda. Reconcilia el mismo intento antes de crear otro."
			}, c(), V(), U();
		}, 15e3));
	};
	function V() {
		q && (q.textContent = a.auto ? "Pausar giro" : "Giro suave", q.disabled = !!a.draft), A.replaceChildren(), A.dataset.state = a.status?.status ?? "ready", A.append(b("span", a.status?.message ?? `${n.nodes.length} conceptos · ${n.edges.length} relaciones persistidas. Girar y filtrar no escribe en MongoDB.`));
		let e = n.nodes.find((e) => e.key === a.selected);
		e && !u(n, a).some((t) => t.key === e.key) && (A.append(b("p", "El concepto está guardado y queda fuera de los filtros activos.")), x("Mostrar concepto guardado", () => {
			a.source = "", a.type = "", a.relation = "", H(), R(), P.bringFront(e.key);
		}, A)), a.pending?.action === "edit" && a.status?.status === "partial" && x("Revisar edición parcial con mi borrador", () => {
			a.pending = void 0, a.status = {
				status: "conflict",
				message: "La ficha parcial permanece guardada. Revisa los datos actuales antes de reenviar el contenido."
			}, c(), U(), V();
		}, A), a.pending && [
			"uncertain",
			"partial",
			"pending"
		].includes(a.status?.status ?? "") && x("Reconciliar el mismo intento", B, A, !0);
	}
	function H() {
		j.replaceChildren();
		let e = {
			value: "",
			text: "Todos"
		};
		C(j, "Fuente visible", [e, ...[...new Set(n.nodes.map((e) => e.source))].sort().map((e) => ({
			value: e,
			text: e
		}))], a.source, (e) => {
			a.source = e, R();
		}), C(j, "Tipo visible", [e, ...[...new Set(n.nodes.map((e) => e.tipo))].sort().map((e) => ({
			value: e,
			text: e
		}))], a.type, (e) => {
			a.type = e, R();
		}), C(j, "Relación visible", [e, ...n.relation_types.map((e) => ({
			value: e,
			text: e
		}))], a.relation, (e) => {
			a.relation = e, R();
		});
	}
	function U() {
		if (O.replaceChildren(), a.draft) {
			W(a.draft);
			return;
		}
		let e = n.nodes.find((e) => e.key === a.selected);
		if (!e) {
			O.append(b("h3", "Encuentra una idea"), b("p", "Selecciona un concepto o crea el primero sobre la esfera."));
			return;
		}
		O.append(b("h3", e.titulo, "selected-title"), b("p", `${e.tipo} · ${e.source}`, "identity"), b("p", e.key, "identity"), b("p", e.contenido_latex, "content")), e.comentario && O.append(b("p", e.comentario, "content"));
		let t = b("div", "", "actions");
		O.append(t), x("Editar ficha", () => L("edit"), t, !0), x("Crear conectado", () => L("create_connected", a.points[e.key]), t), x("Conectar con…", () => L("connect"), t), x("Abrir nota / edición avanzada", () => {
			c(), i("open_note", {
				key: e.key,
				nonce: crypto.randomUUID()
			});
		}, t), O.append(b("h3", "Vecinos reales"));
		let r = f(n, e.key);
		r.length || O.append(b("p", "Todavía no tiene conexiones.")), r.forEach((t) => {
			let r = n.edges.filter((n) => n.from === e.key && n.to === t.key || n.to === e.key && n.from === t.key).map((t) => `${t.from === e.key ? "→" : "←"} ${t.tipo}`);
			x(`${t.titulo} · ${r.join(", ")}`, () => I(t.key), O).className = "neighbor";
		});
	}
	function W(e) {
		let t = {
			create: "Crear concepto aquí",
			create_connected: "Crear concepto conectado",
			connect: "Conectar conceptos",
			edit: "Editar ficha"
		}[e.action];
		O.append(b("h3", t));
		let r = b("form");
		r.onsubmit = (e) => {
			e.preventDefault(), z();
		}, O.append(r);
		let i = (t, n) => {
			e[t] = n, c(), P.request();
		};
		if (e.action !== "connect") {
			let t = S(r, "Nombre", e.title, (e) => i("title", e));
			t.required = !0, t.maxLength = 500, e.action !== "edit" && (C(r, "Source administrada", n.sources.map((e) => ({
				value: e.id,
				text: e.name
			})), e.source, (e) => i("source", e)), C(r, "Tipo de concepto", n.concept_types.map((e) => ({
				value: e,
				text: e
			})), e.type, (e) => i("type", e)), n.sources.length || r.append(b("p", "Crea una Source activa desde «Añadir Source» antes de guardar.", "hint")));
			let a = S(r, "Contenido (texto o LaTeX)", e.content, (e) => i("content", e), !0);
			a.required = !0, a.maxLength = 1e5;
			let o = b("details");
			o.append(b("summary", "Opcionales")), r.append(o), S(o, "Categorías separadas por comas", e.categories, (e) => i("categories", e)), S(o, "Comentario", e.comment, (e) => i("comment", e), !0);
		}
		(e.action === "connect" || e.action === "create_connected") && G(r, e, i), a.status?.status === "conflict" && e.action === "edit" && x("Revisar versión actual y conservar mi borrador", () => {
			let t = n.nodes.find((t) => t.key === e.origin);
			t && (r.append(b("p", `Versión actual: ${t.titulo}\n${t.contenido_latex}`, "content")), x("He revisado: basar mi borrador en esta versión", () => {
				e.revision = t.revision, a.status = {
					status: "draft",
					message: "Versión revisada. El borrador sigue sin enviar."
				}, R();
			}, r));
		}, r);
		let o = b("div", "", "actions");
		r.append(o);
		let s = b("button", "Guardar", "primary");
		s.type = "submit", s.disabled = !!a.pending || e.action.startsWith("create") && !n.sources.length, o.append(s);
		let l = x("Cancelar borrador", () => {
			if (!a.pending) {
				let e = a.draft?.submitted;
				a.draft = void 0, a.status = {
					status: "ready",
					message: e ? "Borrador cerrado; las escrituras ya confirmadas se conservan." : "Borrador cancelado; no se envió ninguna escritura."
				}, R();
			}
		}, o);
		l.disabled = !!a.pending, a.pending && Array.from(r.querySelectorAll("input,textarea,select")).forEach((e) => {
			e.disabled = !0;
		});
	}
	function G(e, t, r) {
		t.action === "connect" && C(e, "Destino", [{
			value: "",
			text: "Elegir concepto"
		}, ...n.nodes.map((e) => ({
			value: e.key,
			text: `${e.titulo} · ${e.source}`
		}))], t.target, (e) => {
			r("target", e), s();
		}), C(e, "Tipo de relación", n.relation_types.map((e) => ({
			value: e,
			text: e
		})), t.relation, (e) => {
			r("relation", e), s();
		});
		let i = b("label", "Invertir sentido "), a = b("input");
		a.type = "checkbox", a.checked = t.reverse, a.onchange = () => {
			r("reverse", a.checked), s();
		}, i.append(a), e.append(i);
		let o = b("p", "", "preview");
		e.append(o);
		function s() {
			let e = n.nodes.find((e) => e.key === t.origin)?.titulo ?? t.origin, r = t.action === "connect" ? n.nodes.find((e) => e.key === t.target)?.titulo ?? "Destino" : t.title || "Nuevo concepto";
			o.textContent = `${t.reverse ? r : e} → [${t.relation}] → ${t.reverse ? e : r} · propuesta sin guardar`;
		}
		e.addEventListener("input", s), s();
	}
	let K = x(a.flat ? "Esfera S²" : "Plano", () => {
		a.flat = !a.flat, K.textContent = a.flat ? "Esfera S²" : "Plano", R();
	}, T);
	x("Crear concepto aquí", () => L("create"), T, !0);
	let q = x(a.auto ? "Pausar giro" : "Giro suave", () => {
		a.selected = "", a.auto = !a.auto, R();
	}, T);
	x("− Zoom", () => {
		a.camera.zoom = Math.max(.5, a.camera.zoom - .15), F();
	}, T), x("+ Zoom", () => {
		a.camera.zoom = Math.min(2.5, a.camera.zoom + .15), F();
	}, T), x("Restablecer vista", () => {
		a.camera = {
			yaw: 0,
			pitch: 0,
			zoom: 1
		}, P.pause(), R();
	}, T);
	let J = b("div", "", "search");
	T.append(J);
	let Y = [{
		value: "",
		text: "Buscar o seleccionar concepto"
	}, ...n.nodes.map((e) => ({
		value: e.key,
		text: `${e.titulo} · ${e.source}`
	}))], X = C(J, "Seleccionar concepto", Y, a.selected, (e) => {
		e && I(e);
	});
	S(J, "Buscar nombre o ID", "", (e) => {
		P.pause(), X.replaceChildren(), Y.filter((t) => !t.value || (t.text + t.value).toLocaleLowerCase().includes(e.toLocaleLowerCase())).forEach((e) => {
			let t = b("option", e.text);
			t.value = e.value, X.append(t);
		});
	}).setAttribute("type", "search"), H(), U(), V(), c();
	let Z = () => {
		P.destroy(), N && clearTimeout(N), c();
	};
	return y.set(t, Z), Z;
}
//#endregion
export { T as default };
