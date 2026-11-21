//#region src/knowledge-map/geometry.ts
var e = Math.PI * 2;
function t(e, t) {
	return e < t ? -1 : +(e > t);
}
function n(e) {
	let t = Math.hypot(...e);
	return t < 1e-10 ? [
		0,
		0,
		1
	] : e.map((e) => e / t);
}
function r([e, t, n], r) {
	let i = Math.cos(r.yaw) * e + Math.sin(r.yaw) * n, a = -Math.sin(r.yaw) * e + Math.cos(r.yaw) * n;
	return [
		i,
		Math.cos(r.pitch) * t - Math.sin(r.pitch) * a,
		Math.sin(r.pitch) * t + Math.cos(r.pitch) * a
	];
}
function i([e, t, n], r) {
	let i = -Math.sin(r.pitch) * t + Math.cos(r.pitch) * n;
	return [
		Math.cos(r.yaw) * e - Math.sin(r.yaw) * i,
		Math.cos(r.pitch) * t + Math.sin(r.pitch) * n,
		Math.sin(r.yaw) * e + Math.cos(r.yaw) * i
	];
}
function a(e, t) {
	return {
		...t,
		yaw: -Math.atan2(e[0], e[2]),
		pitch: Math.atan2(e[1], Math.hypot(e[0], e[2]))
	};
}
function o(e, t, n, i, a = !1) {
	let o = Math.min(n, i) * .38 * t.zoom;
	if (a) return {
		x: n / 2 + Math.atan2(e[0], e[2]) / Math.PI * o,
		y: i / 2 - Math.asin(e[1]) / (Math.PI / 2) * o,
		z: 1
	};
	let [s, c, l] = r(e, t);
	return {
		x: n / 2 + s * o,
		y: i / 2 - c * o,
		z: l
	};
}
function s(e, t, r, a, o) {
	let s = Math.min(a, o) * .38 * r.zoom, c = (e - a / 2) / s, l = -(t - o / 2) / s;
	return n(i(n([
		c,
		l,
		Math.sqrt(Math.max(0, 1 - c * c - l * l))
	]), r));
}
function c(e, r, i) {
	let a = { ...r }, o = [...e].sort(t), s = Object.keys(r).length > 0;
	return o.forEach((e, t) => {
		if (a[e]) return;
		let r = 1 - 2 * (t + .5) / o.length, c = t * Math.PI * (3 - Math.sqrt(5)), l = o.length === 1 ? [
			0,
			0,
			1
		] : n([
			Math.cos(c) * Math.sqrt(1 - r * r),
			r,
			Math.sin(c) * Math.sqrt(1 - r * r)
		]);
		i?.key === e && (l = n(i.point));
		let u = s || i?.key === e ? Object.values(a) : [];
		for (let e = 0; e < 48 && u.some((e) => Math.hypot(e[0] - l[0], e[1] - l[1], e[2] - l[2]) < .09); e++) l = n([
			l[0] + .11 * Math.cos(e * 2.4),
			l[1] + .11 * Math.sin(e * 2.4),
			l[2]
		]);
		a[e] = l;
	}), a;
}
function l(t, r, i = 0, a = !1) {
	let o = Math.max(-1, Math.min(1, t.reduce((e, t, n) => e + t * r[n], 0))), s = Math.abs(t[1]) < .8 ? [
		0,
		1,
		0
	] : [
		1,
		0,
		0
	], c = n([
		t[1] * s[2] - t[2] * s[1],
		t[2] * s[0] - t[0] * s[2],
		t[0] * s[1] - t[1] * s[0]
	]);
	if (a || o > .99999) return Array.from({ length: 33 }, (r, a) => {
		let o = a / 32 * e, l = .1 + Math.abs(i) * .04;
		return n(t.map((e, t) => e + c[t] * Math.sin(o) * l + s[t] * (1 - Math.cos(o)) * l));
	});
	let l = Math.acos(o), u = Math.sin(l);
	return Array.from({ length: 25 }, (e, a) => {
		let o = a / 24;
		return n((u < 1e-4 ? t.map((e, t) => Math.cos(Math.PI * o) * e + Math.sin(Math.PI * o) * c[t]) : t.map((e, t) => (Math.sin((1 - o) * l) * e + Math.sin(o * l) * r[t]) / u)).map((e, t) => e + i * .035 * Math.sin(Math.PI * o) * c[t]));
	});
}
//#endregion
//#region src/knowledge-map/model.ts
function u() {
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
function d(e, t) {
	return e.nodes.filter((e) => (!t.source || e.source === t.source) && (!t.type || e.tipo === t.type));
}
function f(e, t, n) {
	let r = new Set(t.map((e) => e.key));
	return e.edges.filter((e) => r.has(e.from) && r.has(e.to) && (!n.relation || e.tipo === n.relation));
}
function p(e, t) {
	let n = /* @__PURE__ */ new Set();
	return e.edges.forEach((e) => {
		e.from === t && n.add(e.to), e.to === t && n.add(e.from);
	}), e.nodes.filter((e) => n.has(e.key));
}
function m(e, t, n, r) {
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
function h(e, t) {
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
function g(e, t) {
	let n = e.result;
	!n || n.operation_id !== t.pending?.operation_id || (t.status = n, n.status === "saved" || n.status === "duplicate" ? (n.key && (t.selected = n.key), t.acknowledged = n.operation_id, t.pending = void 0, t.draft = void 0) : (n.status === "conflict" || n.status === "invalid") && (t.pending = void 0));
}
//#endregion
//#region src/knowledge-map/canvas.ts
var _ = {
	definicion: "#65e5ce",
	teorema: "#ffe29a",
	proposicion: "#7abfff",
	corolario: "#d0b4ff",
	lema: "#ffa3b5",
	ejemplo: "#ffbd72",
	nota: "#bfccd9"
}, v = class {
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
	labelBoxes = [];
	controller = new AbortController();
	resize;
	intersection;
	motion = window.matchMedia("(prefers-reduced-motion: reduce)");
	constructor(e, t, n, r, i, a) {
		this.canvas = e, this.data = t, this.view = n, this.select = r, this.create = i, this.changed = a;
		let o = e.getContext("2d");
		if (!o) throw Error("Canvas no disponible; usa los formularios accesibles.");
		this.context = o;
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
			this.create(s(t.clientX - r.left, t.clientY - r.top, n.camera, this.width, this.height));
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
		this.data = e, this.nodes = d(e, this.view);
		let n = /* @__PURE__ */ new Map();
		this.paths = f(e, this.nodes, this.view).map((e) => {
			let r = [e.from, e.to].sort(t).join("\0"), i = n.get(r) ?? 0;
			return n.set(r, i + 1), {
				from: e.from,
				to: e.to,
				points: l(this.view.points[e.from], this.view.points[e.to], i, e.from === e.to)
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
		this.pause(), this.view.camera = a(this.view.points[e], this.view.camera), this.request();
	}
	draw(e) {
		if (this.frame = 0, this.stopped || document.hidden || !this.shown) {
			this.lastTime = 0;
			return;
		}
		let t = performance.now(), n = this.context, r = this.view.camera, i = this.view.auto && !this.view.draft && !this.view.selected && !this.motion.matches && !this.view.flat;
		i && this.lastTime && (r.yaw += Math.min(e - this.lastTime, 50) * 45e-6), this.lastTime = e, n.clearRect(0, 0, this.width, this.height);
		let a = Math.min(this.width, this.height) * .38 * r.zoom;
		n.strokeStyle = "#26485c", n.lineWidth = 1, this.view.flat || (n.beginPath(), n.arc(this.width / 2, this.height / 2, a, 0, Math.PI * 2), n.stroke()), this.drawEdges(n), this.projected.clear();
		let s = this.nodes.map((e) => ({
			node: e,
			point: o(this.view.points[e.key], r, this.width, this.height, this.view.flat)
		})).sort((e, t) => e.point.z - t.point.z);
		this.labelBoxes = [];
		let c = s.find(({ node: e }) => e.key === this.view.selected);
		if (c && this.labelBoxes.push(this.labelBox(n, c.node, c.point)), s.forEach(({ node: e, point: t }) => this.drawNode(n, e, t)), this.drawProposal(n), this.view.draft && this.view.draft.action.startsWith("create")) {
			let e = o(this.view.draft.point, r, this.width, this.height, this.view.flat);
			n.globalAlpha = .9, n.strokeStyle = "#ffffff", n.setLineDash([4, 4]), n.beginPath(), n.arc(e.x, e.y, 12, 0, Math.PI * 2), n.stroke(), n.setLineDash([]), n.fillStyle = "#ffffff", n.fillText("Borrador", e.x + 16, e.y);
		}
		n.globalAlpha = 1, this.canvas.dataset.renderMs = String(performance.now() - t), i && this.request();
	}
	drawProposal(e) {
		let t = this.view.draft;
		if (!t || !["connect", "create_connected"].includes(t.action)) return;
		let n = this.view.points[t.origin], r = t.action === "connect" ? this.view.points[t.target] : t.point;
		!n || !r || (e.globalAlpha = .85, e.strokeStyle = "#f5dc9b", e.lineWidth = 2, e.setLineDash([5, 5]), e.beginPath(), l(n, r).forEach((t, n) => {
			let r = o(t, this.view.camera, this.width, this.height, this.view.flat);
			n === 0 ? e.moveTo(r.x, r.y) : e.lineTo(r.x, r.y);
		}), e.stroke(), e.setLineDash([]));
	}
	drawEdges(e) {
		let t = this.paths.map((e) => ({
			strong: [this.hover, this.view.selected].some((t) => !!t && (e.from === t || e.to === t)),
			points: e.points.map((e) => o(e, this.view.camera, this.width, this.height, this.view.flat))
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
	labelBox(e, t, n) {
		let r = t.titulo.length > 37 ? t.titulo.slice(0, 35) + "…" : t.titulo;
		e.font = "bold 13px system-ui";
		let i = e.measureText(r).width;
		return {
			x: Math.max(4, Math.min(n.x + 13, this.width - i - 4)),
			y: n.y - 9,
			width: i
		};
	}
	drawNode(e, t, n) {
		this.projected.set(t.key, n);
		let r = t.key === this.view.selected, i = r || t.key === this.hover;
		if (e.globalAlpha = n.z < 0 ? .25 : .6 + .4 * n.z, e.fillStyle = _[t.tipo] ?? "#bfccd9", e.beginPath(), e.arc(n.x, n.y, i ? 7 : 3 + (n.z + 1), 0, Math.PI * 2), e.fill(), r && (e.strokeStyle = "#ffffff", e.lineWidth = 2, e.beginPath(), e.arc(n.x, n.y, 11, 0, Math.PI * 2), e.stroke()), i || this.nodes.length < 35 && n.z > .1) {
			let r = this.labelBox(e, t, n);
			if (!i && this.labelBoxes.some((e) => Math.abs(e.y - r.y) < 17 && r.x < e.x + e.width + 5 && r.x + r.width + 5 > e.x)) return;
			this.labelBoxes.push(r), e.fillStyle = "#edf9ff", e.font = i ? "bold 13px system-ui" : "12px system-ui";
			let a = t.titulo.length > 37 ? t.titulo.slice(0, 35) + "…" : t.titulo;
			e.fillText(a, r.x, r.y);
		}
	}
	destroy() {
		this.stopped = !0, cancelAnimationFrame(this.frame), this.frame = 0, this.controller.abort(), this.resize.disconnect(), this.intersection.disconnect();
	}
}, y = /* @__PURE__ */ new Map(), b = /* @__PURE__ */ new WeakMap();
function x(e, t = "", n = "") {
	let r = document.createElement(e);
	return r.textContent = t, r.className = n, r;
}
function S(e, t, n, r = !1) {
	let i = x("button", e, r ? "primary" : "");
	return i.type = "button", i.onclick = t, n.append(i), i;
}
function C(e, t, n, r, i = !1) {
	let a = x("label", t), o = x(i ? "textarea" : "input");
	return o.setAttribute("aria-label", t), o.value = n, o.oninput = () => r(o.value), a.append(o), e.append(a), o;
}
function w(e, t, n, r, i) {
	let a = x("label", t), o = x("select");
	return n.forEach((e) => {
		let t = x("option", e.text);
		t.value = e.value, o.append(t);
	}), o.setAttribute("aria-label", t), o.value = r, o.onchange = () => i(o.value), a.append(o), e.append(a), o;
}
function T(e) {
	if (y.has(e)) return y.get(e);
	try {
		let t = JSON.parse(sessionStorage.getItem("mathmongo-map-" + e) ?? "null");
		if (t && t.camera && [
			"yaw",
			"pitch",
			"zoom"
		].every((e) => Number.isFinite(t.camera[e])) && t.points) return t;
	} catch {}
	return u();
}
function E(e) {
	let { parentElement: t, data: n, setTriggerValue: r } = e;
	b.get(t)?.();
	let a = T(n.scope);
	y.set(n.scope, a);
	let o = a.pending && n.result?.key && a.draft ? {
		key: n.result.key,
		point: a.draft.point
	} : void 0;
	a.points = c(n.nodes.map((e) => e.key), a.points, o), g(n, a), a.pending && n.result?.operation_id !== a.pending.operation_id && (a.status = {
		status: "uncertain",
		message: "Existe un envío anterior sin confirmar. Reconcilia el mismo intento antes de continuar."
	});
	let s = () => {
		try {
			sessionStorage.setItem("mathmongo-map-" + n.scope, JSON.stringify(a));
		} catch {}
	}, l = x("section", "", "knowledge-map");
	l.setAttribute("aria-label", "Mapa de conocimiento editable");
	let u = x("div", "Una idea abre un camino", "eyebrow");
	l.append(u, x("h2", "Tu conocimiento, conectado"));
	let f = x("div", "", "toolbar"), E = x("div", "", "layout"), D = x("div", "", "stage"), O = x("aside"), k = x("canvas");
	k.tabIndex = 0, k.setAttribute("role", "img"), k.setAttribute("aria-label", "Superficie del conocimiento. Flechas para girar; usa el selector para elegir conceptos.");
	let A = x("div", "", "status");
	A.setAttribute("role", "status"), A.setAttribute("aria-live", "polite");
	let j = x("div", "", "filters");
	l.append(f, j, A, E), E.append(D, O), D.append(k), D.append(x("p", "Arrastra para girar · flechas con el mapa enfocado · clic derecho para crear aquí", "hint"));
	let M = x("div", "", "legend");
	Object.entries(_).forEach(([e, t]) => {
		let n = x("span", e);
		n.style.setProperty("--node-color", t), M.append(n);
	}), D.append(M), (t.querySelector(".knowledge-map-root") ?? t).replaceChildren(l);
	let N, P = new v(k, n, a, (e) => I(e), (e) => L("create", e), () => {
		s(), q && (q.textContent = a.auto ? "Pausar giro" : "Giro suave");
	}), F = () => {
		P.update(n), s();
	}, I = (e) => {
		if (a.draft) {
			a.status = {
				status: "draft",
				message: "Conserva o cancela el borrador antes de cambiar la selección."
			}, V();
			return;
		}
		a.selected = e, X.value = e, P.bringFront(e), U(), F(), V();
	}, L = (e, t = i([
		0,
		0,
		1
	], a.camera)) => {
		if (a.pending || a.draft) return;
		P.pause();
		let r = c([...n.nodes.map((e) => e.key), "__draft__"], a.points, {
			key: "__draft__",
			point: t
		}).__draft__;
		a.draft = m(n, a, e, r), a.status = {
			status: "draft",
			message: "Borrador: aún no se ha escrito en la base."
		}, U(), V(), F();
	}, R = () => {
		U(), V(), F();
	}, z = () => {
		!a.draft || a.pending || (a.draft.submitted = !0, a.pending = h(a.draft, crypto.randomUUID()), B());
	}, B = () => {
		a.pending && (a.status = {
			status: "saving",
			message: "Guardando… espera la confirmación. El envío ya no se puede cancelar."
		}, s(), V(), U(), r("intent", a.pending), N = setTimeout(() => {
			a.status = {
				status: "uncertain",
				message: "La confirmación tarda. Reconcilia el mismo intento antes de crear otro."
			}, s(), V(), U();
		}, 15e3));
	};
	function V() {
		q && (q.textContent = a.auto ? "Pausar giro" : "Giro suave", q.disabled = !!a.draft), A.replaceChildren(), A.dataset.state = a.status?.status ?? "ready", A.append(x("span", a.status?.message ?? `${n.nodes.length} conceptos · ${n.edges.length} relaciones persistidas. Girar y filtrar no escribe en MongoDB.`));
		let e = n.nodes.find((e) => e.key === a.selected);
		e && !d(n, a).some((t) => t.key === e.key) && (A.append(x("p", "El concepto está guardado y queda fuera de los filtros activos.")), S("Mostrar concepto guardado", () => {
			a.source = "", a.type = "", a.relation = "", H(), R(), P.bringFront(e.key);
		}, A)), a.pending?.action === "edit" && a.status?.status === "partial" && S("Revisar edición parcial con mi borrador", () => {
			a.pending = void 0, a.status = {
				status: "conflict",
				message: "La ficha parcial permanece guardada. Revisa los datos actuales antes de reenviar el contenido."
			}, s(), U(), V();
		}, A), a.pending && [
			"uncertain",
			"partial",
			"pending"
		].includes(a.status?.status ?? "") && S("Reconciliar el mismo intento", B, A, !0);
	}
	function H() {
		j.replaceChildren();
		let e = {
			value: "",
			text: "Todos"
		};
		w(j, "Fuente visible", [e, ...[...new Set(n.nodes.map((e) => e.source))].sort((e, t) => e.localeCompare(t, "es")).map((e) => ({
			value: e,
			text: e
		}))], a.source, (e) => {
			a.source = e, R();
		}), w(j, "Tipo visible", [e, ...[...new Set(n.nodes.map((e) => e.tipo))].sort((e, t) => e.localeCompare(t, "es")).map((e) => ({
			value: e,
			text: e
		}))], a.type, (e) => {
			a.type = e, R();
		}), w(j, "Relación visible", [e, ...n.relation_types.map((e) => ({
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
			O.append(x("h3", "Encuentra una idea"), x("p", "Selecciona un concepto o crea el primero sobre la esfera."));
			return;
		}
		O.append(x("h3", e.titulo, "selected-title"), x("p", `${e.tipo} · ${e.source}`, "identity"), x("p", e.key, "identity"), x("p", e.contenido_latex, "content")), e.comentario && O.append(x("p", e.comentario, "content"));
		let t = x("div", "", "actions");
		O.append(t), S("Editar ficha", () => L("edit"), t, !0), S("Crear conectado", () => L("create_connected", a.points[e.key]), t), S("Conectar con…", () => L("connect"), t), S("Abrir nota / edición avanzada", () => {
			s(), r("open_note", {
				key: e.key,
				nonce: crypto.randomUUID()
			});
		}, t), O.append(x("h3", "Vecinos reales"));
		let i = p(n, e.key);
		i.length || O.append(x("p", "Todavía no tiene conexiones.")), i.forEach((t) => {
			let r = n.edges.filter((n) => n.from === e.key && n.to === t.key || n.to === e.key && n.from === t.key).map((t) => `${t.from === e.key ? "→" : "←"} ${t.tipo}`);
			S(`${t.titulo} · ${r.join(", ")}`, () => I(t.key), O).className = "neighbor";
		});
	}
	function W(e) {
		let t = {
			create: "Crear concepto aquí",
			create_connected: "Crear concepto conectado",
			connect: "Conectar conceptos",
			edit: "Editar ficha"
		}[e.action];
		O.append(x("h3", t));
		let r = x("form");
		r.onsubmit = (e) => {
			e.preventDefault(), z();
		}, O.append(r);
		let i = (t, n) => {
			e[t] = n, s(), P.request();
		};
		if (e.action !== "connect") {
			let t = C(r, "Nombre", e.title, (e) => i("title", e));
			t.required = !0, t.maxLength = 500, e.action !== "edit" && (w(r, "Source administrada", n.sources.map((e) => ({
				value: e.id,
				text: e.name
			})), e.source, (e) => i("source", e)), w(r, "Tipo de concepto", n.concept_types.map((e) => ({
				value: e,
				text: e
			})), e.type, (e) => i("type", e)), n.sources.length || r.append(x("p", "Crea una Source activa desde «Añadir Source» antes de guardar.", "hint")));
			let a = C(r, "Contenido (texto o LaTeX)", e.content, (e) => i("content", e), !0);
			a.required = !0, a.maxLength = 1e5;
			let o = x("details");
			o.append(x("summary", "Opcionales")), r.append(o), C(o, "Categorías separadas por comas", e.categories, (e) => i("categories", e)), C(o, "Comentario", e.comment, (e) => i("comment", e), !0);
		}
		(e.action === "connect" || e.action === "create_connected") && G(r, e, i), a.status?.status === "conflict" && e.action === "edit" && S("Revisar versión actual y conservar mi borrador", () => {
			let t = n.nodes.find((t) => t.key === e.origin);
			t && (r.append(x("p", `Versión actual: ${t.titulo}\n${t.contenido_latex}`, "content")), S("He revisado: basar mi borrador en esta versión", () => {
				e.revision = t.revision, a.status = {
					status: "draft",
					message: "Versión revisada. El borrador sigue sin enviar."
				}, R();
			}, r));
		}, r);
		let o = x("div", "", "actions");
		r.append(o);
		let c = x("button", "Guardar", "primary");
		c.type = "submit", c.disabled = !!a.pending || e.action.startsWith("create") && !n.sources.length, o.append(c);
		let l = S("Cancelar borrador", () => {
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
		t.action === "connect" && w(e, "Destino", [{
			value: "",
			text: "Elegir concepto"
		}, ...n.nodes.map((e) => ({
			value: e.key,
			text: `${e.titulo} · ${e.source}`
		}))], t.target, (e) => {
			r("target", e), s();
		}), w(e, "Tipo de relación", n.relation_types.map((e) => ({
			value: e,
			text: e
		})), t.relation, (e) => {
			r("relation", e), s();
		});
		let i = x("label", "Invertir sentido "), a = x("input");
		a.type = "checkbox", a.checked = t.reverse, a.onchange = () => {
			r("reverse", a.checked), s();
		}, i.append(a), e.append(i);
		let o = x("p", "", "preview");
		e.append(o);
		function s() {
			let e = n.nodes.find((e) => e.key === t.origin)?.titulo ?? t.origin, r = t.action === "connect" ? n.nodes.find((e) => e.key === t.target)?.titulo ?? "Destino" : t.title || "Nuevo concepto";
			o.textContent = `${t.reverse ? r : e} → [${t.relation}] → ${t.reverse ? e : r} · propuesta sin guardar`;
		}
		e.addEventListener("input", s), s();
	}
	let K = S(a.flat ? "Esfera S²" : "Plano", () => {
		a.flat = !a.flat, K.textContent = a.flat ? "Esfera S²" : "Plano", R();
	}, f);
	S("Crear concepto aquí", () => L("create"), f, !0);
	let q = S(a.auto ? "Pausar giro" : "Giro suave", () => {
		a.selected = "", a.auto = !a.auto, R();
	}, f);
	S("− Zoom", () => {
		a.camera.zoom = Math.max(.5, a.camera.zoom - .15), F();
	}, f), S("+ Zoom", () => {
		a.camera.zoom = Math.min(2.5, a.camera.zoom + .15), F();
	}, f), S("Restablecer vista", () => {
		a.camera = {
			yaw: 0,
			pitch: 0,
			zoom: 1
		}, P.pause(), R();
	}, f);
	let J = x("div", "", "search");
	f.append(J);
	let Y = [{
		value: "",
		text: "Buscar o seleccionar concepto"
	}, ...n.nodes.map((e) => ({
		value: e.key,
		text: `${e.titulo} · ${e.source}`
	}))], X = w(J, "Seleccionar concepto", Y, a.selected, (e) => {
		e && I(e);
	});
	C(J, "Buscar nombre o ID", "", (e) => {
		P.pause(), X.replaceChildren(), Y.filter((t) => !t.value || (t.text + t.value).toLocaleLowerCase().includes(e.toLocaleLowerCase())).forEach((e) => {
			let t = x("option", e.text);
			t.value = e.value, X.append(t);
		});
	}).setAttribute("type", "search"), H(), U(), V(), s();
	let Z = () => {
		P.destroy(), N && clearTimeout(N), s();
	};
	return b.set(t, Z), Z;
}
//#endregion
export { E as default };
