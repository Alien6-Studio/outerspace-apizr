import json

from apizr.extensions.plugins.api import PipelinePlugin


class DeliveryNote(PipelinePlugin):
    after = "FastApizrStep"

    def execute(self, context):
        context.result = (
            "delivery_note",
            json.dumps(
                {
                    "api_module": context.data["api_module"],
                    "project": context.options.get("project", "sample"),
                },
                sort_keys=True,
            )
            + "\n",
        )
        context.write_output("delivery_note", "delivery.json")
        return context
