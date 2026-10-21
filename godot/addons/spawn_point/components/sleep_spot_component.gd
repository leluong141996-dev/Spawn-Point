class_name SleepSpotComponent
extends Node
## A bed: a [FarmerComponent]'s interact here sleeps until morning (see [FarmDaysComponent]).

const SP_NAME := "SleepSpot"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["sleep"]
const SP_CATEGORY := "core"

## Emitted when someone goes to sleep here.
signal slept()


func _ready() -> void:
	get_parent().add_to_group(&"sleep_spot")


## Sleeps through to the next morning. Returns false when there is no farming season to move on.
func sleep() -> bool:
	for e in get_tree().get_nodes_in_group(SP.ENTITY_GROUP):
		var days := SP.component(e, &"FarmDays") as FarmDaysComponent
		if days:
			days.sleep()
			slept.emit()
			return true
	return false
