"""
Source:
  - traproyalties-new1/api/ddex/generator.py  (DDEXGenerator)
  - traproyalties-new1/api/ddex/validator.py  (validate_ern, validate_release_data)

Self-contained — only stdlib. The 'TrapRoyaltiesPro' sender label and message-id prefix
are now constructor arguments so the engine can stamp messages on behalf of any caller.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.etree.ElementTree as ET
from xml.dom import minidom


ERN_NAMESPACES = {
    "4.3": {
        "xmlns": "http://ddex.net/xml/ern/43",
        "xmlns:xs": "http://www.w3.org/2001/XMLSchema-instance",
        "xs:schemaLocation": "http://ddex.net/xml/ern/43 http://ddex.net/xml/ern/43/release-notification.xsd",
        "MessageSchemaVersionId": "ern/43",
    },
    "3.8": {
        "xmlns": "http://ddex.net/xml/ern/382",
        "xmlns:xs": "http://www.w3.org/2001/XMLSchema-instance",
        "xs:schemaLocation": "http://ddex.net/xml/ern/382 http://ddex.net/xml/ern/382/release-notification.xsd",
        "MessageSchemaVersionId": "ern/382",
    },
}

REQUIRED_HEADER_FIELDS = ["MessageId", "MessageSender", "MessageCreatedDateTime", "MessageControlType"]
REQUIRED_RELEASE_FIELDS = ["ReleaseReference", "ReferenceTitle", "ReleaseType", "DisplayArtist"]
REQUIRED_SR_FIELDS = ["ResourceReference", "Type", "ReferenceTitle", "Duration"]


def _pretty_xml(element: Element) -> str:
    raw = tostring(element, encoding="unicode")
    return minidom.parseString(raw).toprettyxml(indent="  ", encoding=None)


class DDEXGenerator:
    def __init__(
        self,
        version: str = "4.3",
        message_prefix: str = "ENG",
        recipient: str = "Engine Distribution",
    ):
        if version not in ERN_NAMESPACES:
            raise ValueError(f"Unsupported DDEX version: {version}. Choose '4.3' or '3.8'.")
        self.version = version
        self.message_prefix = message_prefix
        self.recipient = recipient

    def generate(self, release_data: Dict) -> Dict:
        message_id = f"{self.message_prefix}-{release_data.get('id', str(uuid.uuid4())[:8])}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        ns = ERN_NAMESPACES[self.version]

        root = Element("NewReleaseMessage")
        for attr, val in ns.items():
            root.set(attr, val)
        root.set("LanguageAndScriptCode", "en")
        root.set(
            "ReleaseProfileVersionId",
            "CommonReleaseTypes/14/AudioSingle" if self.version == "4.3" else "CommonReleaseTypes/13/AudioSingle",
        )

        self._add_message_header(root, message_id, release_data)
        SubElement(root, "UpdateIndicator").text = "OriginalMessage"
        self._add_party_list(root, release_data)
        self._add_resource_list(root, release_data)
        self._add_release_list(root, release_data, message_id)
        self._add_deal_list(root, release_data)

        xml_str = _pretty_xml(root)
        return {
            "xml": xml_str,
            "hash": hashlib.sha256(xml_str.encode()).hexdigest(),
            "message_id": message_id,
            "version": self.version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _add_message_header(self, root: Element, message_id: str, data: Dict):
        header = SubElement(root, "MessageHeader")
        SubElement(header, "MessageThreadId").text = message_id
        SubElement(header, "MessageId").text = message_id
        SubElement(header, "MessageSender").text = data.get("label_name", "Unknown Label")
        SubElement(header, "SenderPartyId").text = data.get("label_dpid", "PADPIDAZZZZXXXXXXU")
        SubElement(header, "MessageRecipient").text = self.recipient
        SubElement(header, "MessageCreatedDateTime").text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        SubElement(header, "MessageControlType").text = "LiveMessage"

    def _add_party_list(self, root: Element, data: Dict):
        party_list = SubElement(root, "PartyList")

        artist_party = SubElement(party_list, "Party")
        SubElement(artist_party, "PartyReference").text = f"P{data.get('artist_id', '001')}"
        name_el = SubElement(artist_party, "PartyName")
        SubElement(name_el, "FullName").text = data.get("artist", "Unknown Artist")
        if data.get("artist_isni"):
            pid = SubElement(artist_party, "PartyId")
            SubElement(pid, "ISNI").text = data["artist_isni"]
        if data.get("artist_dpid"):
            pid = SubElement(artist_party, "PartyId")
            SubElement(pid, "DPID").text = data["artist_dpid"]

        label_party = SubElement(party_list, "Party")
        SubElement(label_party, "PartyReference").text = f"P{data.get('label_id', '002')}"
        lname_el = SubElement(label_party, "PartyName")
        SubElement(lname_el, "FullName").text = data.get("label_name", "Unknown Label")
        if data.get("label_dpid"):
            pid = SubElement(label_party, "PartyId")
            SubElement(pid, "DPID").text = data["label_dpid"]

        for idx, contributor in enumerate(data.get("contributors", []), start=3):
            cp = SubElement(party_list, "Party")
            SubElement(cp, "PartyReference").text = f"P{contributor.get('id', str(idx).zfill(3))}"
            cn = SubElement(cp, "PartyName")
            SubElement(cn, "FullName").text = contributor.get("name", "")
            if contributor.get("isni"):
                pid = SubElement(cp, "PartyId")
                SubElement(pid, "ISNI").text = contributor["isni"]
            if contributor.get("ipi"):
                pid = SubElement(cp, "PartyId")
                SubElement(pid, "IPI").text = contributor["ipi"]

    def _add_resource_list(self, root: Element, data: Dict):
        resource_list = SubElement(root, "ResourceList")

        tracks = data.get("tracks") or [{
            "title": data.get("title", "Untitled"),
            "isrc": data.get("isrc", ""),
            "duration": data.get("duration", "PT3M00S"),
            "contributors": {},
            "featured_artists": [],
        }]

        role_map = {
            "producer": "Producer",
            "songwriter": "Author",
            "composer": "Composer",
            "mixer": "Mixer",
            "engineer": "RecordingEngineer",
        }

        for idx, track in enumerate(tracks, start=1):
            sr = SubElement(resource_list, "SoundRecording")
            SubElement(sr, "ResourceReference").text = f"R{idx}"
            SubElement(sr, "Type").text = "MusicalWorkSoundRecording"

            sr_id = SubElement(sr, "SoundRecordingId")
            if track.get("isrc"):
                SubElement(sr_id, "ISRC").text = track["isrc"]

            ref_title = SubElement(sr, "ReferenceTitle")
            SubElement(ref_title, "TitleText").text = track.get("title", data.get("title", "Untitled"))

            SubElement(sr, "Duration").text = track.get("duration", "PT3M00S")

            da = SubElement(sr, "DisplayArtist")
            SubElement(da, "PartyReference").text = f"P{data.get('artist_id', '001')}"
            SubElement(da, "DisplayArtistRole").text = "MainArtist"
            SubElement(da, "ArtistPartyReference").text = f"P{data.get('artist_id', '001')}"

            for feat in track.get("featured_artists", []):
                feat_da = SubElement(sr, "DisplayArtist")
                SubElement(feat_da, "PartyReference").text = f"P{feat.get('id', '')}"
                SubElement(feat_da, "DisplayArtistRole").text = "FeaturedArtist"

            for role_key, ddex_role in role_map.items():
                for person in track.get("contributors", {}).get(role_key, []):
                    rc = SubElement(sr, "ResourceContributor")
                    SubElement(rc, "PartyReference").text = f"P{person.get('id', '')}"
                    SubElement(rc, "ResourceContributorRole").text = ddex_role

            SubElement(sr, "LabelName").text = data.get("label_name", "")
            audio_ref = track.get("audio_file", track.get("title", ""))
            audio_hash = hashlib.sha256(audio_ref.encode()).hexdigest()
            hash_el = SubElement(sr, "HashSum")
            SubElement(hash_el, "Algorithm").text = "SHA-256"
            SubElement(hash_el, "HashSumValue").text = audio_hash
            SubElement(sr, "IsInstrumental").text = "false"
            SubElement(sr, "LanguageOfPerformance").text = track.get("language", "en")

    def _add_release_list(self, root: Element, data: Dict, message_id: str):
        release_list = SubElement(root, "ReleaseList")
        release = SubElement(release_list, "Release")
        SubElement(release, "ReleaseReference").text = "R0"

        rel_id = SubElement(release, "ReleaseId")
        if data.get("upc"):
            SubElement(rel_id, "UPC").text = data["upc"]
        if data.get("grid"):
            SubElement(rel_id, "GRid").text = data["grid"]
        if data.get("icpn"):
            SubElement(rel_id, "ICPN").text = data["icpn"]

        ref_title = SubElement(release, "ReferenceTitle")
        SubElement(ref_title, "TitleText").text = data.get("title", "Untitled Release")
        SubElement(release, "ReleaseType").text = data.get("type", "Single")

        da = SubElement(release, "DisplayArtist")
        SubElement(da, "PartyReference").text = f"P{data.get('artist_id', '001')}"
        SubElement(da, "DisplayArtistRole").text = "MainArtist"

        SubElement(release, "LabelName").text = data.get("label_name", "")

        if data.get("release_date"):
            SubElement(release, "GlobalOriginalReleaseDate").text = data["release_date"]

        res_list_el = SubElement(release, "ReleaseResourceReferenceList")
        tracks = data.get("tracks", [{}])
        for idx in range(max(len(tracks), 1)):
            ref_el = SubElement(res_list_el, "ReleaseResourceReference")
            ref_el.text = f"R{idx + 1}"
            ref_el.set("ReleaseResourceType", "PrimaryResource")

        if data.get("genre"):
            genre_el = SubElement(release, "Genre")
            SubElement(genre_el, "GenreText").text = data["genre"]

        SubElement(release, "ParentalWarningType").text = data.get("parental_warning", "NotExplicit")

    def _add_deal_list(self, root: Element, data: Dict):
        deal_list = SubElement(root, "DealList")
        territory_deals = data.get("territory_deals") or {
            "Worldwide": {
                "commercial_model": "SubscriptionModel",
                "usage": ["Stream", "Download"],
                "start_date": data.get("release_date", datetime.now().strftime("%Y-%m-%d")),
            }
        }

        for territory, deal_data in territory_deals.items():
            release_deal = SubElement(deal_list, "ReleaseDeal")
            SubElement(release_deal, "DealReleaseReference").text = "R0"

            deal = SubElement(release_deal, "Deal")
            deal_terms = SubElement(deal, "DealTerms")
            SubElement(deal_terms, "CommercialModelType").text = deal_data.get("commercial_model", "SubscriptionModel")

            for usage in deal_data.get("usage", ["Stream"]):
                u_el = SubElement(deal_terms, "Usage")
                SubElement(u_el, "UseType").text = usage

            SubElement(deal_terms, "TerritoryCode").text = territory

            validity = SubElement(deal_terms, "ValidityPeriod")
            SubElement(validity, "StartDate").text = deal_data.get(
                "start_date", data.get("release_date", datetime.now().strftime("%Y-%m-%d"))
            )
            if deal_data.get("end_date"):
                SubElement(validity, "EndDate").text = deal_data["end_date"]

            for holder in deal_data.get("rights_holders", []):
                rights = SubElement(deal, "RightsController")
                SubElement(rights, "PartyReference").text = f"P{holder.get('id', '')}"
                SubElement(rights, "RightSharePercentage").text = str(holder.get("percentage", 0))
                SubElement(rights, "RightsControllerRole").text = holder.get("role", "RightsController")


def export_ddex(release_data: Dict, version: str = "4.3") -> bytes:
    gen = DDEXGenerator(version=version)
    return gen.generate(release_data)["xml"].encode("utf-8")


def validate_release_data(data: Dict) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not data.get("title"):
        errors.append("Release title is required")
    if not data.get("artist"):
        errors.append("Artist name is required")
    if not data.get("release_date"):
        errors.append("Release date is required")
    if not data.get("label_name"):
        errors.append("Label name is required")
    for i, track in enumerate(data.get("tracks", [])):
        if not track.get("title"):
            errors.append(f"Track {i+1} is missing a title")
        if not track.get("isrc"):
            errors.append(f"Track {i+1} ({track.get('title', '?')}) is missing an ISRC")
    return len(errors) == 0, errors


def validate_ern(xml_string: str) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as e:
        return False, [f"XML parse error: {e}"]

    tag = root.tag
    ns = tag.split("}")[0] + "}" if "{" in tag else ""

    def find(el, path):
        result = el.find(f"{ns}{path}")
        if result is None:
            result = el.find(path)
        return result

    root_name = tag.replace(f"{{{ns[1:-1]}}}", "") if ns else tag
    if "NewReleaseMessage" not in root_name:
        errors.append(f"Root element must be NewReleaseMessage, got: {root_name}")

    header = find(root, "MessageHeader")
    if header is None:
        errors.append("Missing required element: MessageHeader")
    else:
        for field in REQUIRED_HEADER_FIELDS:
            if find(header, field) is None:
                errors.append(f"MessageHeader missing required field: {field}")

    party_list = find(root, "PartyList")
    if party_list is None:
        errors.append("Missing required element: PartyList")
    elif len(list(party_list)) == 0:
        errors.append("PartyList must contain at least one Party")

    resource_list = find(root, "ResourceList")
    if resource_list is None:
        errors.append("Missing required element: ResourceList")
    else:
        srs = resource_list.findall(f"{ns}SoundRecording") or resource_list.findall("SoundRecording")
        for sr in srs:
            for field in REQUIRED_SR_FIELDS:
                if find(sr, field) is None:
                    errors.append(f"SoundRecording missing required field: {field}")

    release_list = find(root, "ReleaseList")
    if release_list is None:
        errors.append("Missing required element: ReleaseList")
    else:
        rels = release_list.findall(f"{ns}Release") or release_list.findall("Release")
        for release in rels:
            for field in REQUIRED_RELEASE_FIELDS:
                if find(release, field) is None:
                    errors.append(f"Release missing required field: {field}")

    if find(root, "DealList") is None:
        errors.append("Missing required element: DealList")

    return len(errors) == 0, errors
