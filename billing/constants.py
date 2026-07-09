FEATURE_MEMBERSHIPS_WRITE = "memberships.write"
FEATURE_NOTES_WRITE = "notes.write"

PLAN_CATALOG = {
	"starter": {
		"name": "Starter",
		"description": "For solo operators and early validation.",
		"monthly_price": 0,
		"features": [FEATURE_MEMBERSHIPS_WRITE, FEATURE_NOTES_WRITE],
	},
	"growth": {
		"name": "Growth",
		"description": "For small teams collaborating inside one workspace.",
		"monthly_price": 29,
		"features": [FEATURE_MEMBERSHIPS_WRITE, FEATURE_NOTES_WRITE],
	},
	"scale": {
		"name": "Scale",
		"description": "For larger teams preparing for production rollout.",
		"monthly_price": 99,
		"features": [FEATURE_MEMBERSHIPS_WRITE, FEATURE_NOTES_WRITE],
	},
}
