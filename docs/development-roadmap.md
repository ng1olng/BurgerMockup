# Development Roadmap

**Status**: Live (as of 2026-06-06)

This document tracks phases, milestones, and progress for the Burger Print project (vendored Open WebUI v0.9.6).

---

## Phase 0: Vendor & Foundation (COMPLETED)

**Objective**: Establish a clean, stable vendoring of Open WebUI v0.9.6 with minimal repo structure.

**Status**: ✅ COMPLETE

### Deliverables

- ✅ Vendored Open WebUI v0.9.6 at `src/open-webui/` (~310K LOC intact)
- ✅ Minimal root structure (README, .gitignore, .claude/)
- ✅ Docker multi-stage build (Node 22 → Python 3.11-slim)
- ✅ docker-compose variants (base, gpu, api, data, otel)
- ✅ Development scripts (npm dev, ./dev.sh)
- ✅ Healthcheck endpoint (`/health`)
- ✅ Initialization documentation (6 docs in `./docs/`)

### Key Decisions

1. **No forking**: Vendored snapshot only; upstream updates intentional, not continuous
2. **Backend-first customization**: FastAPI routers are primary extension point
3. **Docker-first**: Compose variants handle most production scenarios
4. **Static SPA**: adapter-static for frontend (no SSR overhead)

### Lessons Learned

- Open WebUI's middleware stack is complex but well-separated (`utils/middleware.py`)
- 30 routers provide extensive flexibility without requiring code modifications
- Alembic schema versioning is mature (46 migrations tracked cleanly)
- Vector DB abstraction supports 15+ backends (no lock-in risk)

---

## Phase 1: Branding & Customization (PLANNED)

**Objective**: Apply "Burger" branding and prepare for company-specific mockups.

**Target**: Q3 2026 (end of July)

**Status**: 🔵 NOT STARTED

### Scope

- [ ] **Visual Assets** — Logo, color scheme, typography (Figma or design system)
- [ ] **UI Customization** — Custom header/footer, branded colors in components
- [ ] **Deployment Config** — Company infra integration (secrets, domain, SSL certs)
- [ ] **Custom Auth** — OAuth/OIDC integration (if required)
- [ ] **Documentation** — Brand guidelines, deployment runbook

### Estimated Effort

- Design/branding: 1–2 weeks
- Frontend customization: 1–2 weeks
- Deployment/infra: 1 week
- Testing & QA: 1 week

### Dependencies

- Phase 0 complete (✅)
- Design assets finalized
- Auth requirements documented

### Success Criteria

- Logo appears in header/favicon
- Color scheme applied to UI (dark/light modes)
- Custom auth flow (if needed) working end-to-end
- Deployment tested on target infrastructure
- Documentation published for team

---

## Phase 2: Feature Development (PLACEHOLDER)

**Objective**: Extend Open WebUI with custom features (TBD by business requirements).

**Target**: Q3–Q4 2026

**Status**: 🔵 NOT STARTED (pending requirements)

### Possible Features (Not Committed)

- [ ] **Custom Tool Integration** — Company-specific APIs (e.g., CRM, analytics)
- [ ] **Advanced RAG** — Custom embeddings, proprietary knowledge sources
- [ ] **Workflow Automation** — Scheduled tasks, conditional logic
- [ ] **Audit & Compliance** — Enhanced logging, data retention policies
- [ ] **Multi-tenancy** — Organization-scoped chats, knowledge, models
- [ ] **Performance Tuning** — Caching strategies, indexing optimization
- [ ] **Security Hardening** — Data encryption at rest, encryption key management, MFA

### Estimated Effort

- Per feature: 1–4 weeks depending on complexity
- Testing & documentation: +30% per feature

### Dependencies

- Phase 1 complete (branding)
- Feature requirements documented in PDR

### Success Criteria

- Features tested in staging environment
- Backward compatible with Phase 0 (no breaking changes to Open WebUI)
- Documentation updated with new endpoints/stores
- Code review passed per standards in `code-standards.md`

---

## Phase 3: Production Deployment (PLACEHOLDER)

**Objective**: Deploy to production infrastructure with monitoring and runbooks.

**Target**: Q4 2026 (after Phases 1–2)

**Status**: 🔵 NOT STARTED

### Scope

- [ ] **Infrastructure** — K8s cluster, databases, vector DBs, CDN
- [ ] **Secrets Management** — Vault or cloud provider secrets
- [ ] **Monitoring & Alerts** — Prometheus, Grafana, OTel integration
- [ ] **Backup & Disaster Recovery** — RTO/RPO targets, runbooks
- [ ] **Performance Testing** — Load testing, latency baseline
- [ ] **Security Audit** — STRIDE analysis, penetration testing
- [ ] **Compliance** — GDPR, HIPAA (if applicable)

### Estimated Effort

- Infra setup: 2–3 weeks
- Monitoring: 1 week
- Security audit: 1–2 weeks
- Testing & runbooks: 1 week

### Dependencies

- Phase 2 complete (feature development)
- Production infrastructure provisioned
- Security & compliance requirements finalized

### Success Criteria

- 99.9% uptime SLA baseline established
- All features verified in production-like staging
- On-call runbooks documented and tested
- Security audit sign-off obtained

---

## Phase 4: Optimization & Scale (PLACEHOLDER)

**Objective**: Optimize for performance, cost, and operational efficiency.

**Target**: Q1 2027+

**Status**: 🔵 NOT STARTED

### Scope

- [ ] **Database Optimization** — Index tuning, query optimization, caching strategy
- [ ] **Vector DB Tuning** — Embedding model selection, reranking, similarity thresholds
- [ ] **Cost Optimization** — Reserved capacity, auto-scaling policies, storage cleanup
- [ ] **Observability Maturity** — SLOs, error budgets, postmortems process
- [ ] **Developer Experience** — CI/CD improvements, local dev setup, debugging tools

### Estimated Effort

- Per optimization: 2–4 weeks
- Measurement & refinement: ongoing

### Dependencies

- Phase 3 complete (prod deployment)
- Production metrics collected (6+ months baseline)

### Success Criteria

- P99 latency under SLA targets
- Cost per user < budget threshold
- MTTR (mean time to recovery) < 30 minutes
- Developer onboarding time < 1 hour

---

## Milestones & Timeline

| Milestone | Target Date | Phase | Status |
|-----------|-------------|-------|--------|
| **Vendor & Docs** | 2026-06-06 | 0 | ✅ DONE |
| **Branding Ready** | 2026-07-31 | 1 | 🔵 Planned |
| **Initial Features** | 2026-09-30 | 2 | 🔵 Planned |
| **Prod Deployment** | 2026-12-31 | 3 | 🔵 Planned |
| **Performance SLA** | 2027-03-31 | 4 | 🔵 Planned |

---

## Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|-----------|
| **Open WebUI upstream breaks** | High | Low | Keep vendored; selective cherry-pick critical fixes |
| **Vector DB performance** | High | Medium | Benchmark multiple backends before Phase 2 |
| **Auth complexity** | Medium | Medium | Use Open WebUI's OAuth/OIDC; avoid custom flows if possible |
| **Scaling database** | Medium | Medium | Plan PostgreSQL replication before Phase 3 |
| **Security audit delays** | High | Medium | Engage auditors early in Phase 2 |
| **Budget overrun** | High | Medium | Track effort per phase, course-correct early |

---

## Success Metrics (Phase 0+)

### Availability & Performance

- **Uptime**: ≥ 99.5% (Phase 0), ≥ 99.9% (Phase 3+)
- **API Latency P99**: < 500ms (chat), < 200ms (RAG search)
- **Page Load**: < 2s (SPA)
- **WebSocket Reconnect**: < 5s

### Adoption & Usage

- **User Onboarding**: < 5 min to first chat
- **Feature Discovery**: 80% users find key features within 1 session
- **Chat Retention**: ≥ 70% 7-day active users

### Operational

- **Incident Response**: MTTR < 30 minutes (Phase 3+)
- **Deployment Frequency**: ≥ 1 per week
- **Code Coverage**: ≥ 80% (new code)
- **Documentation Up-to-Date**: ≥ 95% (quarterly review)

### Cost

- **Cost per 1000 API calls**: < $0.10 (goal, depends on model pricing)
- **Infrastructure Cost**: < $10K/month (Phase 3 baseline)
- **TCO (total cost of ownership)**: TBD based on Phase 3 actuals

---

## Unresolved Decisions

1. **Embedding Model** — Fine-tuned for specific domain, or multi-model approach?
2. **Vector DB** — Self-hosted (Qdrant, Milvus) or managed (Pinecone)?
3. **Database Strategy** — PostgreSQL only, or multi-database support?
4. **Custom Auth** — Integrate with company directory (LDAP/OIDC), or use Open WebUI's OAuth?
5. **Multi-tenancy** — From day 1, or Phase 2+ if needed?
6. **Billing Model** — Per-user, per-token, per-organization?
7. **Regional Deployment** — Single region initially, multi-region Phase 3+?

---

## Review Schedule

- **Monthly**: Phase status, risk updates
- **Quarterly**: Roadmap adjustment, success metrics review
- **Annually**: Strategic reassessment, Phase 1–4 reprioritization

**Last Updated**: 2026-06-06
**Next Review**: 2026-07-06
