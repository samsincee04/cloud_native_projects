module.exports = [
"[externals]/next/dist/compiled/next-server/app-route-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-route-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/compiled/next-server/app-page-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-page-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-unit-async-storage.external.js [external] (next/dist/server/app-render/work-unit-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-unit-async-storage.external.js", () => require("next/dist/server/app-render/work-unit-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-async-storage.external.js [external] (next/dist/server/app-render/work-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-async-storage.external.js", () => require("next/dist/server/app-render/work-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/shared/lib/no-fallback-error.external.js [external] (next/dist/shared/lib/no-fallback-error.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/shared/lib/no-fallback-error.external.js", () => require("next/dist/shared/lib/no-fallback-error.external.js"));

module.exports = mod;
}),
"[project]/app/api/summarize/route.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "POST",
    ()=>POST
]);
async function POST(request) {
    const backendBaseUrl = process.env.BACKEND_BASE_URL;
    const devJwtToken = process.env.DEV_JWT_TOKEN;
    if (!backendBaseUrl || !devJwtToken) {
        return new Response(JSON.stringify({
            error: "Server configuration error"
        }), {
            status: 500,
            headers: {
                "Content-Type": "application/json"
            }
        });
    }
    const body = await request.json();
    const text = typeof body.prompt === "string" ? body.prompt.trim() : "";
    if (!text) {
        return new Response(JSON.stringify({
            error: "Prompt is required"
        }), {
            status: 400,
            headers: {
                "Content-Type": "application/json"
            }
        });
    }
    const res = await fetch(`${backendBaseUrl}/summarize`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${devJwtToken}`
        },
        body: JSON.stringify({
            text,
            max_length: 100
        })
    });
    if (!res.ok) {
        const errText = await res.text();
        return new Response(JSON.stringify({
            error: errText || `Backend error: ${res.status}`
        }), {
            status: res.status,
            headers: {
                "Content-Type": "application/json"
            }
        });
    }
    const data = await res.json();
    return new Response(data.summary, {
        headers: {
            "Content-Type": "text/plain; charset=utf-8"
        }
    });
}
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__c384f73f._.js.map