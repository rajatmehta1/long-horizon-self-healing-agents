
### Scenario 1 - Auto Approve and transient ready small order
python -m app.trigger start ORDER-SMALL-001 'My USB-C laptop arrived with the packaging completely1 crushed. The stand wobbles and is not usable.'


### Scenario 2 - Human Approval when refund is above 500$
python -m app.trigger start ORDER-MID-002 'I received my ProBook laptop. But the screen has a large crack in it and i cant use it at all. Need a refund.'

python -m app.trigger status customer-support-ORDER-MID-002

python -m app.trigger approve customer-support-ORDER-MID-002 alice.smith "Shipping damage confirmed"

### Scenario 3 - Human Approval REJECTION
python -m app.trigger start ORDER-MID-002 'I received my ProBook laptop. But the screen has a large crack in it and i cant use it at all. Need a refund.'

python -m app.trigger status customer-support-ORDER-MID-002

python -m app.trigger reject customer-support-ORDER-MID-002 alice.smith "Photos show item arrived in new condition. Damage after usage."

### worked dies
worker process dies and restarts

python -m app.trigger start ORDER-SMALL-001 'My USB-C laptop arrived with the packaging completely1 crushed. The stand wobbles and is not usable.'
