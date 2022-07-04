import asyncio
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from tkinter import filedialog, messagebox, simpledialog
from typing import Literal

import byml
import imgui
import libyaz0
import pygui  # py-gui-tool
import SarcLib
from appdirs import user_config_dir


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


window = pygui.Window(
    "Super Mario Odyssey Modding Tool", 800, 600, resource_path("Roboto-Regular.ttf")
)

loop = asyncio.get_event_loop_policy().get_event_loop()


def folder_checker(elements: pygui.Elements):
    selected = elements.state.get("romfs_path")
    exists = os.path.isdir(elements.state.get("romfs_path", ""))
    good_romfs = (
        exists
        and os.path.isdir(os.path.join(elements.state.get("romfs_path"), "EffectData"))
        and os.path.isdir(os.path.join(elements.state.get("romfs_path"), "EventData"))
        and os.path.isdir(os.path.join(elements.state.get("romfs_path"), "LayoutData"))
        and os.path.isdir(
            os.path.join(elements.state.get("romfs_path"), "LocalizedData")
        )
        and os.path.isdir(os.path.join(elements.state.get("romfs_path"), "MovieData"))
        and os.path.isdir(os.path.join(elements.state.get("romfs_path"), "ObjectData"))
        and os.path.isdir(os.path.join(elements.state.get("romfs_path"), "ShaderData"))
        and os.path.isdir(os.path.join(elements.state.get("romfs_path"), "SoundData"))
        and os.path.isdir(os.path.join(elements.state.get("romfs_path"), "StageData"))
        and os.path.isdir(os.path.join(elements.state.get("romfs_path"), "SystemData"))
    )
    if not selected:
        elements.text("A RomFS folder must be selected.")
        return False
    if not exists:
        elements.text("RomFS path does not exist!")
        return False
    if not good_romfs:
        elements.text("RomFS path is not a valid Super Mario Odyssey RomFS!")
        return False
    if not os.path.isdir(elements.state.get("patches_path", "")):
        elements.text("You must select a folder to save the patches to.")
        return False
    return True


def decode_szs(file: str) -> SarcLib.SARC_Archive:
    with open(file, "rb") as f:
        data = f.read()

    while libyaz0.IsYazCompressed(data):
        data = libyaz0.decompress(data)

    archive = SarcLib.SARC_Archive()
    archive.load(data)
    return archive


def export_szs(archive: SarcLib.SARC_Archive, path: str) -> None:
    data = archive.save()[0]
    data = libyaz0.compress(data)
    if not os.path.exists(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    with open(path, "wb") as f:
        f.write(data)


def get_file(path: str):
    patches_path = os.path.join(window.state.get("patches_path", ""), path)
    romfs_path = os.path.join(window.state.get("romfs_path", ""), path)
    if os.path.exists(patches_path):
        return patches_path
    return romfs_path


def get_file_from_szs(szs: SarcLib.SARC_Archive, path: str):
    for file in szs.contents:
        if isinstance(file, SarcLib.FileArchive.File) and file.name == path:
            return file
    return None


def edit_shop_save(state: pygui.elements.State):
    shop_data_szs = state.get("shop_data_szs")
    shop_data = state.get("shop_data")
    be = state.get("shop_data_be")
    for item in shop_data:
        item["Price"] = byml.Int(state.get(item["ItemName"] + "Price", item["Price"]))
    data = byml.Writer(shop_data, be, 3).get_bytes()
    get_file_from_szs(shop_data_szs, "ItemList.byml").data = data
    export_szs(
        shop_data_szs,
        os.path.join(state.get("patches_path"), "SystemData", "ItemList.szs"),
    )
    state["shop_editor_loading"] = False


async def run_edit_shop_save(state: pygui.elements.State):
    await loop.run_in_executor(None, edit_shop_save, state)


def stat_editor_save(state: pygui.elements.State):
    player_actor_szs = state.get("player_actor_szs")
    player_const = state.get("player_const")
    be = state.get("player_const_be")
    for key, value in player_const.items():
        player_const[key] = type(value)(state.get("PlayerConstValue" + key))
    data = byml.Writer(player_const, be, 3).get_bytes()
    get_file_from_szs(player_actor_szs, "PlayerConst.byml").data = data
    export_szs(
        player_actor_szs,
        os.path.join(
            state.get("patches_path"), "ObjectData", "PlayerActorHakoniwa.szs"
        ),
    )
    state["player_stat_editor_loading"] = False


async def run_stat_editor_save(state: pygui.elements.State):
    await loop.run_in_executor(None, stat_editor_save, state)


def export_song(state: pygui.elements.State, data, music_info, scenario):
    resource_name = music_info["ResourceName"]
    file_path = get_file(os.path.join("SoundData", "stream", resource_name + ".bfstm"))
    if not os.path.exists(file_path):
        messagebox.showerror("Error", "File not found: " + os.path.normpath(file_path))
        state[
            f"music_editor_export_{data['Name']}_{scenario['ScenarioNo']}_{music_info['Name']}_loading"
        ] = False
        return
    save_to = filedialog.asksaveasfile(
        "wb",
        confirmoverwrite=True,
        defaultextension=".wav",
        title="Export sound to a file (by default wav)",
        filetypes=(
            ("Supported Files", ".wav .mp3 .ogg"),
            (".wav", "Waveform Audio File Format"),
            (".mp3", "MPEG audio Layer-3"),
            (".ogg", "Ogg Vorbis Audio File"),
        ),
        initialfile=f"{resource_name}.wav",
    )

    if save_to:
        extension = save_to.name.split(".")[-1]
        audio = AudioTools(file_path)
        output = audio.convert("bfstm")
        if extension == "mp3":
            with open(AudioTools.convert_to_mp3(output), "rb") as f:
                save_to.write(f.read())
        elif extension == "ogg":
            with open(AudioTools.convert_to_ogg(output), "rb") as f:
                save_to.write(f.read())
        else:
            with open(output, "rb") as f:
                save_to.write(f.read())
    state[
        f"music_editor_export_{data['Name']}_{scenario['ScenarioNo']}_{music_info['Name']}_loading"
    ] = False


async def run_export_song(state: pygui.elements.State, data, music_info, scenario):
    await loop.run_in_executor(None, export_song, state, data, music_info, scenario)


def import_song(state: pygui.elements.State, data, music_info, scenario):
    resource_name = music_info["ResourceName"]
    file_path_to_replace = os.path.join(
        state.get("patches_path"), "SoundData", "stream", resource_name + ".bfstm"
    )
    file_to_use = filedialog.askopenfilename(
        defaultextension=".wav",
        title="Import sound from a file (wav files are recommended)",
        filetypes=(
            ("Supported Files", ".wav .mp3 .ogg"),
            (".wav", "Waveform Audio File Format"),
            (".mp3", "MPEG audio Layer-3"),
            (".ogg", "Ogg Vorbis Audio File"),
        ),
        initialfile=f"{resource_name}.wav",
    )

    if file_to_use:
        extension = file_to_use.split(".")[-1]
        if extension == "mp3":
            file_to_use = AudioTools.convert_mp3_to_wav(file_to_use)
        elif extension == "ogg":
            file_to_use = AudioTools.convert_ogg_to_wav(file_to_use)
        audio = AudioTools(file_to_use)
        output = audio.convert(
            "wav",
            simpledialog.askinteger(
                "Number Of Loops",
                "How many times should the song be looped? By default 1",
            )
            or 1,
        )
        if not os.path.exists(os.path.dirname(file_path_to_replace)):
            os.makedirs(os.path.dirname(file_path_to_replace))
        with open(file_path_to_replace, "wb") as f:
            with open(output, "rb") as f2:
                f.write(f2.read())
    state[
        f"music_editor_import_{data['Name']}_{scenario['ScenarioNo']}_{music_info['Name']}_loading"
    ] = False


async def run_import_song(state: pygui.elements.State, data, music_info, scenario):
    await loop.run_in_executor(None, import_song, state, data, music_info, scenario)


class AudioTools:
    vgmstream = resource_path(os.path.join("audio_tools", "vgmstream.exe"))
    vgaudio = resource_path(os.path.join("audio_tools", "vgaudio.exe"))
    ffmpeg = resource_path(os.path.join("audio_tools", "ffmpeg.exe"))
    oggenc = resource_path(os.path.join("audio_tools", "oggenc.exe"))

    def __init__(self, input_file: str) -> None:
        self.input_file = input_file

    def convert(
        self, ext: Literal["bfstm", "wav", "mp3", "ogg"], number_of_loops: int = 1
    ) -> str:
        if ext == "bfstm":
            return self._convert_bfstm(number_of_loops)
        elif ext == "wav":
            return self._convert_wav(number_of_loops)
        elif ext == "mp3":
            old_input_file = self.input_file
            self.input_file = self.convert_mp3_to_wav(self.input_file)
            result = self._convert_wav(number_of_loops)
            self.input_file = old_input_file
            return result
        elif ext == "ogg":
            old_input_file = self.input_file
            self.input_file = self.convert_ogg_to_wav(self.input_file)
            result = self._convert_wav(number_of_loops)
            self.input_file = old_input_file
        else:
            raise ValueError(f"Unknown file format: {ext}")

    def _convert_bfstm(self, _: bool = True) -> str:
        output_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        output_file.close()
        subprocess.call(
            [
                self.vgmstream,
                "-o",
                output_file.name,
                str(self.input_file),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return output_file.name

    def _convert_wav(self, number_of_loops: int = 1) -> str:
        input_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        input_file.close()
        subprocess.call(
            [
                self.ffmpeg,
                "-i",
                str(self.input_file),
                "-af",
                "asetrate=32000",
                str(input_file.name),
                "-y",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        lwav_file = tempfile.NamedTemporaryFile(suffix=".lwav", delete=False)
        lwav_file.close()
        subprocess.call(
            [
                self.vgmstream,
                "-f",
                "0",
                f"-l {number_of_loops}",
                "-L",
                "-o",
                lwav_file.name,
                str(input_file.name),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        output_file = tempfile.NamedTemporaryFile(suffix=".bfstm", delete=False)
        output_file.close()
        subprocess.call(
            [
                self.vgaudio,
                "--little-endian",
                lwav_file.name,
                output_file.name,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return output_file.name

    @staticmethod
    def convert_to_mp3(file: str) -> str:
        temp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        temp.close()
        subprocess.call(
            [AudioTools.ffmpeg, "-i", file, temp.name, "-y"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return temp.name

    @staticmethod
    def convert_to_ogg(file: str) -> str:
        temp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
        temp.close()
        subprocess.call(
            [AudioTools.oggenc, "-o", temp.name, file, "-Q"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return temp.name

    @staticmethod
    def convert_mp3_to_wav(file: str) -> str:
        temp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp.close()
        subprocess.call(
            [AudioTools.ffmpeg, "-i", file, temp.name, "-y"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return temp.name

    @staticmethod
    def convert_ogg_to_wav(file: str) -> str:
        temp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp.close()
        subprocess.call(
            [AudioTools.oggenc, "-o", temp.name, file, "-Q"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return temp.name


@window.menu("File", "Select RomFS Folder", ["Ctrl", "R"])
def select_romfs_folder():
    window.state["romfs_path"] = filedialog.askdirectory(
        initialdir=window.state.get("romfs_path"), mustexist=True, title="RomFS Folder"
    ) or window.state.get("romfs_path", "")


@window.menu("File", "Select Patches Folder", ["Ctrl", "P"])
def select_patches_folder():
    window.state["patches_path"] = filedialog.askdirectory(
        mustexist=True, title="Patches Folder"
    ) or window.state.get("patches_path", "")

@window.menu("Randomize", "Randomize Music")
def randomize_music():
    if not window.state.get("romfs_path"):
        return messagebox.showerror("Error", "No RomFS folder selected")
    if not window.state.get("patches_path"):
        return messagebox.showerror("Error", "No Patches folder selected")
    files = os.listdir(os.path.join(window.state["romfs_path"], "SoundData", "stream"))
    random_files = random.sample(files, len(files))
    
    if not os.path.exists(os.path.join(window.state["patches_path"], "SoundData", "stream")):
        os.makedirs(os.path.join(window.state["patches_path"], "SoundData", "stream"))
    
    for old, new in zip(files, random_files):
        shutil.copyfile(os.path.join(window.state["romfs_path"], "SoundData", "stream", old), os.path.join(window.state["patches_path"], "SoundData", "stream", new))

    messagebox.showinfo("Success", "Randomized music")

@window.frame("Shop Editor", 735, 480, (50, 100))
def shop_editor_frame(elements: pygui.Elements):
    if folder_checker(elements):
        loop.run_until_complete(shop_editor(elements))


@window.frame("Player Stat Editor", 735, 480, (10, 70))
def player_stat_editor_frame(elements: pygui.Elements):
    if folder_checker(elements):
        loop.run_until_complete(player_stat_editor(elements))


@window.frame("Music Editor", 735, 480, (20, 80))
def music_editor_frame(elements: pygui.Elements):
    if folder_checker(elements):
        loop.run_until_complete(music_editor(elements))


async def shop_editor(elements: pygui.Elements):
    shop_data_szs = elements.state.get("shop_data_szs")
    if not shop_data_szs:
        elements.state["shop_data_szs"] = shop_data_szs = decode_szs(
            get_file(os.path.join("SystemData", "ItemList.szs"))
        )
    shop_data = elements.state.get("shop_data")
    if not shop_data:
        data = byml.Byml(get_file_from_szs(shop_data_szs, "ItemList.byml").data)
        elements.state["shop_data_be"] = data._be
        elements.state["shop_data"] = shop_data = data.parse()
    elements.text("Shop Editor", font_size=76)

    imgui.columns(3, "shopeditor")
    imgui.separator()

    elements.text("Name")
    imgui.next_column()

    elements.text("Price")
    imgui.next_column()

    elements.text("Store")
    imgui.next_column()

    imgui.separator()

    for item in list({v["ItemName"]: v for v in shop_data}.values()):
        imgui.text(item["ItemName"])
        imgui.next_column()
        elements.input_int(
            "", int(item["Price"]), key=item["ItemName"] + "Price", maximum=9999
        )
        imgui.next_column()
        imgui.text(item.get("StoreName", "All"))
        imgui.next_column()

    imgui.columns(1)

    @elements.button(
        "Loading..." if elements.state.get("shop_editor_loading") else "Save"
    )
    def shop_save_button():
        elements.state["shop_editor_loading"] = True
        loop.create_task(run_edit_shop_save(elements.state))


async def player_stat_editor(elements: pygui.Elements):
    player_actor_szs = elements.state.get("player_actor_szs")
    if not player_actor_szs:
        elements.state["player_actor_szs"] = player_actor_szs = decode_szs(
            get_file(os.path.join("ObjectData", "PlayerActorHakoniwa.szs"))
        )
    player_const = elements.state.get("player_const")
    if not player_const:
        found_file = get_file_from_szs(player_actor_szs, "PlayerConst.byml")
        if not found_file:
            player_actor_szs.addFile(
                SarcLib.File(
                    "PlayerConst.byml",
                    open(resource_path("PlayerConst.byml"), "rb").read(),
                )
            )
            found_file = get_file_from_szs(player_actor_szs, "PlayerConst.byml")
        byml_data = byml.Byml(found_file.data)
        elements.state["player_const"] = player_const = byml_data.parse()
        elements.state["player_const_be"] = byml_data._be
    elements.text("Player Stat Editor", font_size=76)

    searched = elements.input_text("Search...", "", key="player_const_search")

    imgui.new_line()

    for key, value in player_const.items():
        if searched.lower() not in key.lower():
            continue
        if isinstance(value, (byml.Float, byml.Double)):
            elements.input_float(key, float(value), key="PlayerConstValue" + key)
        elif isinstance(value, (byml.Int, byml.Int64)):
            elements.input_int(
                key, int(value), key="PlayerConstValue" + key, wrap_text=False
            )

    @elements.button(
        "Loading..." if elements.state.get("player_stat_editor_loading") else "Save"
    )
    def player_stat_editor_save_button():
        elements.state["player_stat_editor_loading"] = True
        loop.create_task(run_stat_editor_save(elements.state))


async def music_editor(elements: pygui.Elements):
    bgm_data_base_szs = elements.state.get("bgm_data_base_szs")
    if not bgm_data_base_szs:
        elements.state["bgm_data_base_szs"] = bgm_data_base_szs = decode_szs(
            get_file(os.path.join("SoundData", "BgmDataBase.szs"))
        )
    bgm_stage_info_list = elements.state.get("bgm_stage_info_list")
    if not bgm_stage_info_list:
        byml_data = byml.Byml(
            get_file_from_szs(bgm_data_base_szs, "BgmStageInfoList.byml").data
        )
        elements.state["bgm_stage_info_list"] = bgm_stage_info_list = byml_data.parse()
        elements.state["bgm_stage_info_list_be"] = byml_data._be
    elements.text("Music Editor", font_size=76)

    searched = elements.input_text("Search...", "", key="music_editor_search")

    imgui.new_line()

    for data in bgm_stage_info_list["StageInfoList"]:
        if searched.lower() not in data["Name"].lower():
            continue
        imgui.bullet_text(data["Name"])
        imgui.indent()
        imgui.indent()
        for scenario in data["StageScenarioInfoList"]:
            imgui.bullet_text(f"Scenario Number: {scenario['ScenarioNo']}")
            imgui.indent()
            imgui.indent()
            for music_info in scenario["StagePlayInfoList"]:
                imgui.bullet_text(f"Name: {music_info['Name']}")

                imgui.same_line()

                @elements.button(
                    "Loading..."
                    if elements.state.get(
                        f"music_editor_export_{data['Name']}_{scenario['ScenarioNo']}_{music_info['Name']}_loading"
                    )
                    else "Export",
                    key=f"music_editor_export_{data['Name']}_{scenario['ScenarioNo']}_{music_info['Name']}",
                )
                def export_button():
                    elements.state[
                        f"music_editor_export_{data['Name']}_{scenario['ScenarioNo']}_{music_info['Name']}_loading"
                    ] = True
                    loop.create_task(
                        run_export_song(elements.state, data, music_info, scenario)
                    )

                imgui.same_line()

                @elements.button(
                    "Loading..."
                    if elements.state.get(
                        f"music_editor_import_{data['Name']}_{scenario['ScenarioNo']}_{music_info['Name']}_loading"
                    )
                    else "Import",
                    key=f"music_editor_import_{data['Name']}_{scenario['ScenarioNo']}_{music_info['Name']}",
                )
                def import_button():
                    elements.state[
                        f"music_editor_import_{data['Name']}_{scenario['ScenarioNo']}_{music_info['Name']}_loading"
                    ] = True
                    loop.create_task(
                        run_import_song(elements.state, data, music_info, scenario)
                    )

            imgui.unindent()
            imgui.unindent()
        imgui.unindent()
        imgui.unindent()


storage_directory = user_config_dir("Super Mario Odyssey Modding Tool")

if not os.path.exists(storage_directory):
    os.makedirs(storage_directory)

if os.path.exists(os.path.join(storage_directory, "config.json")):
    with open(os.path.join(storage_directory, "config.json"), "r") as f:
        data = json.load(f)
        window.state["romfs_path"] = data["romfs"]
        window.state["patches_path"] = data["patches"]

try:
    window.start()
finally:
    with open(os.path.join(storage_directory, "config.json"), "w") as f:
        json.dump(
            {
                "romfs": window.state["romfs_path"],
                "patches": window.state["patches_path"],
            },
            f,
        )
