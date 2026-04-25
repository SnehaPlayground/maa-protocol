# Legacy Migration Notes

Legacy helper archived at:
- `archive/whatsapp-assistant-legacy/whatsapp-assistant/`

Useful pieces identified from legacy helper:
- phone normalization logic
- employee/external routing pattern
- lightweight JSON state approach
- existing employee list format

Known limitations of legacy helper:
- not a full runtime-integrated WhatsApp sales system
- no reusable business knowledge pack
- no owner command layer
- no structured lead funnel logging
- no private error-shield workflow
- still attached conceptually to main agent behavior rather than dedicated reusable architecture

Current replacement direction:
- reusable skill in `skills/whatsapp-management/`
- client/business pack in `ops/whatsapp-framework/knowledge/`
- logs in `ops/whatsapp-framework/logs/`
