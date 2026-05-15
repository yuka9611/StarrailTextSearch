from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_ROOT = ROOT / "server"
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from dbBuild.mission_dialogue import MissionDialogueExtractor, TalkSentenceRef


def write_json(root: Path, relative_path: str, payload: object) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class MissionDialogueExtractorTest(unittest.TestCase):
    def build_data_root(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        root = Path(temp_dir.name)
        write_json(root, "ExcelOutput/MainMission.json", [{"MainMissionID": 1, "Name": {"Hash": 10}}])
        write_json(
            root,
            "ExcelOutput/SubMission.json",
            [
                {
                    "SubMissionID": 101,
                    "TargetText": {"Hash": 20},
                    "DescrptionText": {"Hash": 21},
                }
            ],
        )
        write_json(root, "ExcelOutput/PerformanceCG.json", [])
        write_json(root, "ExcelOutput/PerformanceDS.json", [{"PerformanceID": 9001, "PerformancePath": "Config/Level/Mission/1/Act/Act9001.json"}])
        write_json(root, "ExcelOutput/PerformanceSubMissionLink.json", [{"SubMissionID": 101, "PerformanceID": 9001, "PerformanceType": "D"}])
        write_json(root, "ExcelOutput/TutorialGuideData.json", [{"ID": 3001, "DescText": {"Hash": 8001}}])
        write_json(root, "ExcelOutput/TutorialGuideTalkData.json", [])
        write_json(root, "ExcelOutput/TutorialGuideGroup.json", [{"FinishSubMission": 101, "MessageText": {"Hash": 8000}, "TutorialGuideIDList": [3001]}])
        write_json(root, "ExcelOutput/TutorialData.json", [])
        write_json(root, "Config/Level/Mission/1/MissionInfo_1.json", {"SubMissionList": [{"ID": 101, "Progress": 1}]})
        write_json(
            root,
            "Config/Level/Mission/1/Mission_101.json",
            {
                "OnStartSequence": [
                    {
                        "TaskList": [
                            {"$type": "RPG.GameCore.PlayMissionTalk", "MissionTalkList": [{"TalkSentenceID": 1001}]},
                            {"$type": "RPG.GameCore.PlayScreenTransfer", "TextEnabled": True, "TalkSentenceID": 1002},
                            {"$type": "RPG.GameCore.PerformanceTransition", "TalkSentenceID": 1003, "Role": "Player"},
                            {"$type": "RPG.GameCore.PlayFullScreenTransfer", "TextInfo": {"TextList": [{"TalkSentenceID": 1004}]}},
                            {
                                "$type": "RPG.GameCore.PlayOptionTalk",
                                "OptionList": [
                                    {"TalkSentenceID": 2001, "TriggerCustomString": "ChoiceA"},
                                    {"TalkSentenceID": 2002, "TriggerCustomString": "ChoiceB"},
                                ],
                            },
                        ]
                    },
                    {
                        "TaskList": [
                            {"$type": "RPG.GameCore.WaitCustomString", "CustomString": {"Value": "ChoiceA"}},
                            {"$type": "RPG.GameCore.PlayMultiVoiceTalk", "TalkSentenceID": 1005},
                        ]
                    },
                    {
                        "TaskList": [
                            {"$type": "RPG.GameCore.WaitCustomString", "CustomString": {"Value": "ChoiceB"}},
                            {"$type": "RPG.GameCore.SelectMissionItem", "SimpleTalk": {"TalkSentenceID": 1006}, "InfoText": {"Hash": 7001}},
                        ]
                    },
                ]
            },
        )
        write_json(
            root,
            "Config/Level/Mission/1/Act/Act9001.json",
            {"OnStartSequence": [{"TaskList": [{"$type": "RPG.GameCore.PerformanceEndBlackText", "TalkSentenceID": 1007}]}]},
        )
        return temp_dir, root

    def test_extracts_structured_dialogue_options_performance_and_tutorial(self) -> None:
        temp_dir, root = self.build_data_root()
        self.addCleanup(temp_dir.cleanup)
        talks = {
            sentence_id: TalkSentenceRef(sentence_id, speaker_hash, text_hash)
            for sentence_id, speaker_hash, text_hash in [
                (1001, "5001", "6001"),
                (1002, "5002", "6002"),
                (1003, None, "6003"),
                (1004, None, "6004"),
                (1005, "5005", "6005"),
                (1006, "5006", "6006"),
                (1007, None, "6007"),
                (2001, None, "6101"),
                (2002, None, "6102"),
            ]
        }

        context = MissionDialogueExtractor(root, talks).extract_mission(1)

        self.assertEqual(len(context.sections), 1)
        section = context.sections[0]
        self.assertEqual(section.section_id, 101)
        self.assertEqual(section.title_hash, "20")
        self.assertEqual(section.description_hash, "21")
        line_types = [line.line_type for line in section.lines]
        self.assertGreaterEqual(line_types.count("dialogue"), 7)
        self.assertEqual(line_types.count("option"), 2)
        self.assertEqual(line_types.count("narration"), 3)
        player_lines = [line for line in section.lines if line.talk_sentence_id == 1003]
        self.assertEqual(player_lines[0].speaker_text, "开拓者")
        option_lines = [line for line in section.lines if line.line_type == "option"]
        self.assertTrue(all(line.option_group_id for line in option_lines))
        self.assertEqual([line.option_index for line in option_lines], [1, 2])
        branch_lines = [line for line in section.lines if line.branch_index]
        self.assertTrue({line.branch_index for line in branch_lines}.issuperset({1, 2}))
        self.assertIn("Config/Level/Mission/1/Act/Act9001.json", context.story_paths)

    def test_player_role_markers_render_as_dialogue_not_options(self) -> None:
        temp_dir, root = self.build_data_root()
        self.addCleanup(temp_dir.cleanup)
        write_json(
            root,
            "Config/Level/Mission/1/Mission_101.json",
            {
                "OnStartSequence": [
                    {
                        "TaskList": [
                            {
                                "$type": "RPG.GameCore.PlayAndWaitSimpleTalk",
                                "SimpleTalkList": [
                                    {
                                        "TalkSentenceID": 3001,
                                        "TalkRole": {"RoleType": "ROLE_PLAYER"},
                                    }
                                ],
                            },
                            {
                                "$type": "RPG.GameCore.SelectMissionItem",
                                "SimpleTalk": {
                                    "TalkSentenceID": 3002,
                                    "AvatarID": "NPC_Avatar_Lad_PlayerBoy_00",
                                },
                            },
                        ]
                    }
                ]
            },
        )
        talks = {
            3001: TalkSentenceRef(3001, None, "7001"),
            3002: TalkSentenceRef(3002, None, "7002"),
        }

        context = MissionDialogueExtractor(root, talks).extract_mission(1)

        lines = [line for line in context.sections[0].lines if line.talk_sentence_id in {3001, 3002}]
        self.assertEqual([line.line_type for line in lines], ["dialogue", "dialogue"])
        self.assertEqual([line.speaker_text for line in lines], ["开拓者", "开拓者"])
        self.assertTrue(all(line.option_group_id is None for line in lines))

    def test_talk_reference_prefers_graph_containing_matching_talk_sentence_id(self) -> None:
        temp_dir, root = self.build_data_root()
        self.addCleanup(temp_dir.cleanup)
        write_json(
            root,
            "Config/Level/Mission/1/Mission_101.json",
            {
                "OnStartSequence": [
                    {
                        "TaskList": [
                            {
                                "$type": "RPG.GameCore.WaitCustomString",
                                "CustomString": {"Value": "Talk_4001"},
                            }
                        ]
                    }
                ]
            },
        )
        write_json(
            root,
            "Config/Level/Mission/1/Act/Act4000.json",
            {
                "OnStartSequence": [
                    {
                        "TaskList": [
                            {
                                "$type": "RPG.GameCore.PlayAndWaitSimpleTalk",
                                "SimpleTalkList": [
                                    {"TalkSentenceID": 4001},
                                    {"TalkSentenceID": 4002},
                                ],
                            }
                        ]
                    }
                ]
            },
        )
        write_json(
            root,
            "Config/Level/Mission/1/Act/Act4001.json",
            {
                "OnStartSequence": [
                    {
                        "TaskList": [
                            {
                                "$type": "RPG.GameCore.PlayAndWaitSimpleTalk",
                                "SimpleTalkList": [{"TalkSentenceID": 4002}],
                            }
                        ]
                    }
                ]
            },
        )
        talks = {
            4001: TalkSentenceRef(4001, None, "9001"),
            4002: TalkSentenceRef(4002, None, "9002"),
        }

        context = MissionDialogueExtractor(root, talks).extract_mission(1)

        lines = [line for line in context.sections[0].lines if line.talk_sentence_id in {4001, 4002}]
        self.assertEqual([line.talk_sentence_id for line in lines], [4001, 4002])
        self.assertIn("Config/Level/Mission/1/Act/Act4000.json", context.story_paths)


if __name__ == "__main__":
    unittest.main()
