# State Examples

## STATE_0_NEW_LEAD
- First inbound inquiry
- No previous outbound reply from Sneha in the thread

## STATE_1_PROSPECT_REPLIED
- Sneha already sent Email 1
- Prospect replied with context, questions, or interest
- Meeting pitch is now allowed if all safeguards pass

## STATE_2_FOLLOW_UP
- Sneha sent Email 1
- No response for 48 hours
- One reminder allowed

## STATE_3_ESCALATED_OR_WON
- Meeting confirmed
- Complex or advisory query asked
- No response 48 hours after reminder
- Human takeover required

## Ambiguous state examples
- Prospect replied, but thread also contains an unanswered meeting proposal
- Email appears forwarded or partially copied without full history
- Payload location conflicts with signature/location in body
- Duplicate send window is unclear

In ambiguous cases, halt, save to drafts, and alert Partha.
