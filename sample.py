import streamlit as st
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import time

# --- Constants ---
HIGH_RISK_NODE_ID = "HighRiskOfDeath_R"
HIGH_RISK_LABEL_PREFIX = "⚠️ " 
SYMPTOM_NODE_PREFIX = "🩺 "     

MAX_HIGH_RISK_INDICATORS = 0 
HIGH_RISK_TRIGGER_THRESHOLD = 5 # Stop if 5 or more high-risk indicators are "yes"

# --- Session State Initialization ---
def initialize_session_state():
    global MAX_HIGH_RISK_INDICATORS
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "graph" not in st.session_state:
        st.session_state.graph = nx.DiGraph()
    if "question_index" not in st.session_state:
        st.session_state.question_index = 0
    if "current_question_id" not in st.session_state: 
        st.session_state.current_question_id = None 
    if "current_question_id_for_next_prompt" not in st.session_state:
        st.session_state.current_question_id_for_next_prompt = None

    if "confirmed_high_risk_indicators" not in st.session_state:
        st.session_state.confirmed_high_risk_indicators = 0
    
    if "consultation_halted_due_to_risk" not in st.session_state:
        st.session_state.consultation_halted_due_to_risk = False

    if MAX_HIGH_RISK_INDICATORS == 0 and 'HARDCODED_QUESTIONS_AND_UPDATES' in globals():
        count = 0
        for q_data in HARDCODED_QUESTIONS_AND_UPDATES:
            if HIGH_RISK_NODE_ID in q_data.get("links_to", []):
                count +=1
        MAX_HIGH_RISK_INDICATORS = count
    
    # Zoom and Pan State Variables
    if "zoom_level" not in st.session_state: st.session_state.zoom_level = 1.0
    if "view_center_x" not in st.session_state: st.session_state.view_center_x = 0.0
    if "view_center_y" not in st.session_state: st.session_state.view_center_y = 0.0
    if "graph_extent_width" not in st.session_state: st.session_state.graph_extent_width = 1.0
    if "graph_extent_height" not in st.session_state: st.session_state.graph_extent_height = 1.0
    if "graph_content_center_x" not in st.session_state: st.session_state.graph_content_center_x = 0.0
    if "graph_content_center_y" not in st.session_state: st.session_state.graph_content_center_y = 0.0
    if "view_initialized_by_data" not in st.session_state: st.session_state.view_initialized_by_data = False

# --- Chat Management ---
def display_chat_messages():
    default_bot_avatar = "🤖"
    thinking_avatar_for_display = "💡" 
    alert_avatar_for_display = "⚠️" 

    for message in st.session_state.messages:
        avatar_to_use = None
        if message["role"] == "assistant":
            if message.get("type") == "thinking":
                avatar_to_use = thinking_avatar_for_display
            elif message.get("type") == "alert": 
                avatar_to_use = alert_avatar_for_display
            else: 
                avatar_to_use = default_bot_avatar
        with st.chat_message(message["role"], avatar=avatar_to_use):
            st.markdown(message["content"], unsafe_allow_html=True)

# --- Knowledge Graph Management ---
def display_knowledge_graph(container):
    with container:
        graph = st.session_state.graph
        if graph.number_of_nodes() == 0 : 
            st.info("The knowledge pathway will build here as you answer questions.")
            st.session_state.view_initialized_by_data = False
            return

        fig, ax = plt.subplots(figsize=(17, 15)) 
        try:
            pos = nx.nx_agraph.graphviz_layout(graph, prog="sfdp", args="-Goverlap=false -Gsplines=true -Gsep=+35 -Gnodesep=0.7")
        except ImportError:
            pos = nx.spring_layout(graph, k=1.3, iterations=160, seed=42, dim=2, scale=2.2) 
        except Exception: 
            pos = nx.spring_layout(graph, k=1.3, iterations=160, seed=42, dim=2, scale=2.2)

        if not pos or graph.number_of_nodes() == 0:
             ax.text(0.5, 0.5, "Generating graph...", ha='center', va='center')
             st.pyplot(fig); return
        
        xs, ys = zip(*pos.values())
        min_x, max_x = (min(xs) if xs else 0), (max(xs) if xs else 1)
        min_y, max_y = (min(ys) if ys else 0), (max(ys) if ys else 1)
        base_w = (max_x - min_x) if abs(max_x - min_x) > 1e-6 else 1.0
        base_h = (max_y - min_y) if abs(max_y - min_y) > 1e-6 else 1.0
        pad_x, pad_y = base_w * 0.28, base_h * 0.28 
        data_w, data_h = base_w + 2 * pad_x, base_h + 2 * pad_y
        st.session_state.graph_extent_width, st.session_state.graph_extent_height = data_w, data_h
        st.session_state.graph_content_center_x, st.session_state.graph_content_center_y = (min_x + max_x) / 2, (min_y + max_y) / 2
        if not st.session_state.view_initialized_by_data:
            st.session_state.view_center_x, st.session_state.view_center_y = st.session_state.graph_content_center_x, st.session_state.graph_content_center_y
            st.session_state.view_initialized_by_data = True
        
        zl = st.session_state.zoom_level
        vw, vh = st.session_state.graph_extent_width*zl, st.session_state.graph_extent_height*zl
        if vw < 1e-6: vw = 0.1
        if vh < 1e-6: vh = 0.1
        cx, cy = st.session_state.view_center_x, st.session_state.view_center_y
        ax.set_xlim(cx - vw/2, cx + vw/2); ax.set_ylim(cy - vh/2, cy + vh/2)

        node_colors, node_sizes, node_labels_dict, node_edge_colors = [], [], {}, []
        
        color_map = {
            "symptom_present": ("#FFCDD2", "#EF9A9A"),    
            "symptom_absent": ("#C8E6C9", "#A5D6A7"), 
            HIGH_RISK_NODE_ID: ("#B71C1C", "#7F0000"), 
            "risk_category": ("#FFF9C4", "#FFF59D"),   
            "default": ("#F5F5F5", "#E0E0E0")          
        }

        for node, data in graph.nodes(data=True):
            label_text = data.get("label", node)
            typ = data.get("type", "default")
            main_label_part = ""
            if typ == HIGH_RISK_NODE_ID: main_label_part = f"{HIGH_RISK_LABEL_PREFIX}{label_text}"
            elif typ in ["symptom_present", "symptom_absent"]: main_label_part = f"{SYMPTOM_NODE_PREFIX}{label_text}"
            else: main_label_part = label_text
            details_parts = []
            for tag, display_prefix in [("SNOMED_ID","SNOMED:"), ("GPHR_ID","GPHR:"), ("WHO_REF","WHO:"), ("Source", "Source:")]:
                if data.get(tag) and data[tag]: 
                    details_parts.append(f"{display_prefix} {data[tag]}")
            node_labels_dict[node] = main_label_part + ("\n\n" + "\n".join(details_parts) if details_parts else "")
            color_key = HIGH_RISK_NODE_ID if typ == HIGH_RISK_NODE_ID else typ
            default_style, default_size = color_map["default"], 4000 
            style_map_sizes = {
                "symptom_present":5000, "symptom_absent":4500,
                HIGH_RISK_NODE_ID: 6500, "risk_category":5000,
            }
            c, ec = color_map.get(color_key, default_style)
            s = style_map_sizes.get(color_key, default_size)
            node_colors.append(c); node_sizes.append(s); node_edge_colors.append(ec)

        scaled_sizes = [s / (zl**0.55) for s in node_sizes] 
        base_node_font, base_edge_font = 11.5, 9.5 # Slightly increased base_node_font for icon visibility
        label_fs = max(4, base_node_font/(zl**0.45)) 
        edge_label_fs = max(4, base_edge_font/(zl**0.45))
        title_fs = max(14, 22/(zl**0.5))

        nx.draw_networkx_nodes(graph, pos, ax=ax, node_color=node_colors, node_size=scaled_sizes, alpha=0.96, linewidths=2.5, edgecolors=node_edge_colors)

        # Req 1: Edge Color - Updated colormap for more intense red progression
        cmap_colors = [
            (0.0, "#A5D6A7"),  # Softer Green (0 confirmed)
            (0.16, "#FFEE58"), # Yellow (approx 2/12)
            (0.33, "#FFC107"), # Amber (approx 4/12)
            (0.41, "#F44336"), # Red (approx 5/12 - threshold)
            (0.5, "#D32F2F"),  # Darker Red (approx 6/12)
            (1.0, "#B71C1C")   # Very Dark Red (12/12)
        ]
        risk_cmap = mcolors.LinearSegmentedColormap.from_list("risk_cmap", cmap_colors)
        edge_colors_list, edge_widths_list, edge_styles_list = [], [], []
        current_risk_score_normalized = 0
        if MAX_HIGH_RISK_INDICATORS > 0 :
             current_risk_score_normalized = st.session_state.confirmed_high_risk_indicators / MAX_HIGH_RISK_INDICATORS

        for u, v, data in graph.edges(data=True):
            source_node_data = graph.nodes[u]
            source_node_type = source_node_data.get('type')
            edge_color, edge_width, edge_style = "#78909C", 1.8, 'solid' 

            if v == HIGH_RISK_NODE_ID and source_node_type == 'symptom_present':
                edge_color = risk_cmap(current_risk_score_normalized) 
                edge_width = 2.8 + (2.8 * current_risk_score_normalized) # Increased max thickness
            elif v == HIGH_RISK_NODE_ID and source_node_type == 'symptom_absent':
                edge_color = "#CFD8DC"; edge_width = 1.5; edge_style = 'dashed'
            
            edge_colors_list.append(edge_color); edge_widths_list.append(edge_width); edge_styles_list.append(edge_style)
        
        nx.draw_networkx_edges(graph, pos, ax=ax, arrowstyle="-|>", arrowsize=32, edge_color=edge_colors_list, width=edge_widths_list, style=edge_styles_list, connectionstyle="arc3,rad=0.2", node_size=scaled_sizes, alpha=0.92)
        
        label_bboxes = {"bbox": dict(facecolor="mintcream", alpha=0.93, edgecolor='darkslategray', boxstyle="round,pad=0.8")}
        nx.draw_networkx_labels(graph, pos, labels=node_labels_dict, ax=ax, font_size=label_fs, font_weight="normal", clip_on=True, **label_bboxes) 
        
        edge_labels_data = nx.get_edge_attributes(graph, "relation")
        if edge_labels_data:
             nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels_data, ax=ax, font_size=edge_label_fs, font_color="#263238", bbox=dict(facecolor="white", alpha=0.82, edgecolor="none", boxstyle="round,pad=0.4"))
        
        plt.title("Interactive Newborn Health Pathway", fontsize=title_fs, fontweight="bold", color="#37474F")
        ax.set_facecolor("#F8FAFC"); fig.set_facecolor("#F8FAFC") 
        ax.axis("off"); fig.tight_layout(pad=1.8); st.pyplot(fig)

# --- Hardcoded Q&A Logic with Thinking Prompts ---
NODE_DEFS = {
    HIGH_RISK_NODE_ID: {"label": "High Risk of Death", "type": HIGH_RISK_NODE_ID, "GPHR_ID": "NewbornMortalityRisk", "Source": "WHO IMCI Framework"},
    "NeonatalDangerSigns_RC": {"label": "Neonatal Danger Signs", "type": "risk_category", "WHO_REF": "WHO:IMCI-NDS", "Source": "WHO IMCI Guidelines"}
}

HARDCODED_QUESTIONS_AND_UPDATES = [
    {
        "id": "Q1_WeakCryAtBirth", "question_text": "When your baby was born, did they cry weakly or not cry at all right away?",
        "symptom_node": {"id": "WeakCryAtBirth_S", "label": "Weak Cry at Birth", "SNOMED_ID": "289908002", "Source": "Clinical Observation"},
        "links_to": [HIGH_RISK_NODE_ID],
        "thinking_prompts": {"before_question": "A baby's first cry is a vital sign. Let's check on this.", "after_yes": "A weak or absent cry at birth is noted. This can sometimes indicate initial breathing difficulties or stress.", "after_no": "Good, a strong cry is a positive initial sign."}
    },
    {
        "id": "Q2_WeakCryAt5Min", "question_text": "Five minutes after birth, was your baby's cry still weak or were they not crying?",
        "symptom_node": {"id": "WeakCryAt5Min_S", "label": "Weak Cry at 5 min", "SNOMED_ID": "289908002", "Source": "APGAR Assessment Component"},
        "links_to": [HIGH_RISK_NODE_ID],
        "thinking_prompts": {"before_question": "Checking the cry again after a few minutes helps understand if any initial issues are resolving.", "after_yes": "Persistent weak cry at 5 minutes is a concern; it suggests ongoing issues that need attention.", "after_no": "Excellent, improvement or a continued strong cry is what we hope for."}
    },
    {
        "id": "Q3_LowBirthWeight", "question_text": "Do you know how much your baby weighed when they were born? Was it very small (e.g., less than 2.5 kg or 5.5 lbs)?",
        "symptom_node": {"id": "LowBirthWeight_S", "label": "Low Birth Weight", "SNOMED_ID": "276654001", "Source": "Birth Record / WHO Classification"},
        "links_to": [HIGH_RISK_NODE_ID],
        "thinking_prompts": {"before_question": "Birth weight is an important factor for a newborn's health. Let's see about this.", "after_yes": "Low birth weight can make babies more vulnerable to certain health issues.", "after_no": "Okay, not identified as low birth weight."}
    },
    {
        "id": "Q4_PretermBirth", "question_text": "Do you know how many weeks pregnant you were when the baby was born? Was it before 37 weeks?",
        "symptom_node": {"id": "PretermBirth_S", "label": "Preterm Birth", "SNOMED_ID": "39572002", "Source": "Gestational Age Assessment / WHO Definition"},
        "links_to": [HIGH_RISK_NODE_ID],
        "thinking_prompts": {"before_question": "Being born too early (preterm) can also affect a baby's health.", "after_yes": "Preterm birth is noted. These babies often need extra care and monitoring.", "after_no": "Good, born at term is generally associated with fewer immediate complications."}
    },
    {
        "id": "Q5_DrowsyUnconscious", "question_text": "Is your baby very sleepy, hard to wake up, or seems unconscious?",
        "symptom_node": {"id": "DrowsyUnconscious_S", "label": "Drowsy/Unconscious", "SNOMED_ID": "110483000", "Source": "Neonatal Danger Sign (WHO)"},
        "links_to": ["NeonatalDangerSigns_RC", HIGH_RISK_NODE_ID],
        "thinking_prompts": {"before_question": "A baby's level of alertness is a key indicator of their well-being.", "after_yes": "Being very drowsy or hard to wake is a significant danger sign that requires immediate medical attention.", "after_no": "Alertness is a good sign. Noted."}
    },
    {
        "id": "Q6_WeakCryDay1", "question_text": "On the first day after birth, did your baby have a weak cry or not cry much at all?",
        "symptom_node": {"id": "WeakCryDay1_S", "label": "Weak Cry Day 1", "SNOMED_ID": "289908002", "Source": "Clinical Sign"},
        "links_to": ["NeonatalDangerSigns_RC", HIGH_RISK_NODE_ID],
        "thinking_prompts": {"before_question": "Let's check the baby's cry on the first day after birth. This helps assess their ongoing condition.", "after_yes": "A weak cry persisting on the first day can be a sign of underlying issues needing observation or intervention.", "after_no": "A strong cry is reassuring for their general status."}
    },
    {
        "id": "Q7_FeedingDifficulty", "question_text": "Is your baby having trouble latching on, or sucking and swallowing milk effectively?",
        "symptom_node": {"id": "FeedingDifficulty_S", "label": "Feeding Difficulty", "SNOMED_ID": "79850006", "Source": "WHO IMCI Sign"},
        "links_to": ["NeonatalDangerSigns_RC", HIGH_RISK_NODE_ID],
        "thinking_prompts": {"before_question": "Effective feeding is crucial for a newborn's growth and energy. How is feeding going?", "after_yes": "Feeding difficulties are an important issue to address, as they can impact nutrition, hydration, and overall well-being.", "after_no": "Good feeding is a very positive sign of health and development."}
    },
    {
        "id": "Q8_PaleJaundicedSkin", "question_text": "Does your baby's skin look unusually pale (very light) or yellow (jaundiced)?",
        "symptom_node": {"id": "PaleJaundicedSkin_S", "label": "Pale or Jaundiced Skin", "SNOMED_ID": "271442005", "Source": "Clinical Sign"},
        "links_to": ["NeonatalDangerSigns_RC", HIGH_RISK_NODE_ID],
        "thinking_prompts": {"before_question": "Skin color can tell us a lot about a baby's health, including circulation and liver function.", "after_yes": "Unusual skin color like significant paleness or jaundice needs to be evaluated by a doctor promptly.", "after_no": "Normal skin color is a good indicator of general health."}
    },
    {
        "id": "Q9_ChestIndrawing", "question_text": "When your baby breathes, do you see their chest pulling in sharply below their ribs (chest indrawing)?",
        "symptom_node": {"id": "ChestIndrawing_S", "label": "Chest Indrawing", "SNOMED_ID": "248210000", "Source": "WHO IMCI Sign"},
        "links_to": ["NeonatalDangerSigns_RC", HIGH_RISK_NODE_ID],
        "thinking_prompts": {"before_question": "How a baby breathes is very important. Let's check for signs of difficult breathing, like chest indrawing.", "after_yes": "Chest indrawing is a clear sign of respiratory distress and requires urgent medical assessment.", "after_no": "No chest indrawing suggests breathing is not labored, which is good."}
    },
    {
        "id": "Q10_Grunting", "question_text": "Does your baby make a grunting sound with each breath when calm?",
        "symptom_node": {"id": "Grunting_S", "label": "Grunting", "SNOMED_ID": "56018004", "Source": "WHO IMCI Sign"},
        "links_to": ["NeonatalDangerSigns_RC", HIGH_RISK_NODE_ID],
        "thinking_prompts": {"before_question": "Let's listen for any unusual breathing sounds like grunting, which can indicate breathing effort.", "after_yes": "Grunting can be a sign of difficulty breathing and should be checked by a doctor, especially if persistent.", "after_no": "No grunting during calm breathing is a good sign."}
    },
    {
        "id": "Q11_Hypothermia", "question_text": "Does your baby feel cold to the touch, especially hands and feet, even when wrapped?",
        "symptom_node": {"id": "Hypothermia_S", "label": "Hypothermia", "SNOMED_ID": "248500002", "Source": "WHO IMCI Sign"},
        "links_to": ["NeonatalDangerSigns_RC", HIGH_RISK_NODE_ID],
        "thinking_prompts": {"before_question": "A baby's body temperature is important to monitor as they can lose heat easily.", "after_yes": "Feeling cold to the touch (hypothermia) is a danger sign for newborns and needs to be addressed quickly.", "after_no": "Maintaining normal body temperature is good for overall stability."}
    },
    {
        "id": "Q12_UnilateralWeakness", "question_text": "Have you noticed if one of your baby's arms or legs seems weaker or doesn't move as much as the other?",
        "symptom_node": {"id": "UnilateralWeakness_S", "label": "Unilateral Weakness", "SNOMED_ID": "162607003", "Source": "Clinical Neurological Sign"},
        "links_to": ["NeonatalDangerSigns_RC", HIGH_RISK_NODE_ID],
        "thinking_prompts": {"before_question": "Movement and strength symmetry are important neurological checks for any concerns.", "after_yes": "Weakness on one side can indicate a neurological issue and needs to be checked by a doctor for proper diagnosis.", "after_no": "Symmetrical movement and strength are reassuring neurological signs."}
    }
]

def process_answer_and_update_graph(question_id_answered, user_answer_text):
    graph = st.session_state.graph
    q_data = next((q for q in HARDCODED_QUESTIONS_AND_UPDATES if q["id"] == question_id_answered), None)
    if not q_data: return "" 

    user_answer_norm = user_answer_text.strip().lower()
    is_yes = any(indicator in user_answer_norm for indicator in ["yes", "yep", "yeah", "correct", "affirmative", "indeed", "sure", "y"])
    is_no = any(indicator in user_answer_norm for indicator in ["no", "nope", "not", "negative", "don't", "can't", "n"])
    
    symptom_present_previously = False
    s_node_id = q_data["symptom_node"]["id"]
    if graph.has_node(s_node_id) and graph.nodes[s_node_id].get('type') == 'symptom_present':
        symptom_present_previously = True

    symptom_present_now = False 
    if is_yes and not is_no: symptom_present_now = True
    
    if HIGH_RISK_NODE_ID in q_data.get("links_to", []):
        if symptom_present_now and not symptom_present_previously:
            st.session_state.confirmed_high_risk_indicators += 1
        elif not symptom_present_now and symptom_present_previously: 
            st.session_state.confirmed_high_risk_indicators = max(0, st.session_state.confirmed_high_risk_indicators - 1)
    
    s_label = q_data["symptom_node"]["label"]
    s_snomed = q_data["symptom_node"].get("SNOMED_ID")
    s_source = q_data["symptom_node"].get("Source")
    s_type = "symptom_present" if symptom_present_now else "symptom_absent"
    
    node_attrs = {"label":s_label, "type":s_type, "SNOMED_ID":s_snomed, "Source":s_source}
    if not graph.has_node(s_node_id): graph.add_node(s_node_id, **node_attrs)
    else: graph.nodes[s_node_id].update(node_attrs)

    for linked_node_id in q_data["links_to"]:
        if linked_node_id not in NODE_DEFS: continue
        props = NODE_DEFS[linked_node_id]
        if not graph.has_node(linked_node_id): graph.add_node(linked_node_id, **props)
        
        relation_label = "Related To"
        if props["type"] == HIGH_RISK_NODE_ID:
            relation_label = "YES" if symptom_present_now else "No Clear Contribution"
        elif props["type"] == "risk_category":
            relation_label = "Is a Sign Of" if symptom_present_now else "Not Clearly a Sign"
        
        edge_attrs = {'relation': relation_label}
        if graph.has_edge(s_node_id, linked_node_id): graph[s_node_id][linked_node_id].update(edge_attrs)
        else: graph.add_edge(s_node_id, linked_node_id, **edge_attrs)

    st.session_state.view_initialized_by_data = False

    prompts = q_data.get("thinking_prompts", {})
    thinking_response = prompts.get("after_yes", "Noted.") if symptom_present_now else prompts.get("after_no", "Okay, understood.")
    
    if st.session_state.confirmed_high_risk_indicators >= HIGH_RISK_TRIGGER_THRESHOLD:
        st.session_state.consultation_halted_due_to_risk = True
    
    return thinking_response


def get_next_question_and_thinking():
    if st.session_state.get("consultation_halted_due_to_risk", False):
        warning_message = (
            f"⚠️ **High Risk Alert!** Based on the responses, "
            f"{st.session_state.confirmed_high_risk_indicators} significant risk indicators have been identified. "
            f"**It is crucial to consult a healthcare professional immediately.** "
            f"No further automated questions will be asked."
        )
        st.session_state.current_question_id_for_next_prompt = None 
        st.session_state.current_question_id = None 
        return "", warning_message 

    idx = st.session_state.question_index
    thinking_before_current_q = ""
    question_text = ""
    greeting = "Hello! I'm here to help assess potential health risks for a newborn. Let's go through some questions. " if idx == 0 and not st.session_state.messages else ""

    if idx < len(HARDCODED_QUESTIONS_AND_UPDATES):
        q_data = HARDCODED_QUESTIONS_AND_UPDATES[idx]
        thinking_before_current_q = greeting + q_data.get("thinking_prompts", {}).get("before_question", "")
        question_text = f"💬 {q_data['question_text']}"
        st.session_state.current_question_id_for_next_prompt = q_data["id"] 
        st.session_state.question_index += 1 
    else: 
        st.session_state.current_question_id_for_next_prompt = None 
        completion_icon = "✅"
        summary_message = "We've completed the initial set of questions. The visual pathway shows the connections. "
        summary_message += "This is a preliminary guide. Always consult a healthcare provider for medical advice."
        question_text = f"{completion_icon} {summary_message}"
    
    return thinking_before_current_q, question_text

# --- Main App ---
st.set_page_config(layout="wide", page_title="Newborn Health Navigator AI")
initialize_session_state() 

st.title("👶 Newborn Health Navigator AI")
st.markdown("---")
col1, col2 = st.columns([0.48, 0.52]) 

with col1:
    st.subheader("💬 Interactive Health Check")
    chat_container = st.container(height=700, key="chat_container_main") 
    with chat_container:
        display_chat_messages()
    
    prompt_placeholder = "Your answer (e.g., 'Yes' or 'No')..."
    disable_input = False
    if st.session_state.get("consultation_halted_due_to_risk", False):
        prompt_placeholder = "Consultation halted due to high risk. Please seek medical advice."
        disable_input = True
    elif st.session_state.question_index >= len(HARDCODED_QUESTIONS_AND_UPDATES) and \
         st.session_state.get("current_question_id_for_next_prompt") is None:
        prompt_placeholder = "Consultation complete. Type 'reset' to start over."

    prompt = st.chat_input(prompt_placeholder, key="chat_input_main", disabled=disable_input)

    if prompt:
        if prompt.strip().lower() == 'reset':
            for key in list(st.session_state.keys()): del st.session_state[key]
            initialize_session_state(); st.rerun()

        if not disable_input: 
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            thinking_after_prev_answer = ""
            if st.session_state.current_question_id: # This refers to the question just answered
                thinking_after_prev_answer = process_answer_and_update_graph(st.session_state.current_question_id, prompt)
            
            if thinking_after_prev_answer:
                 st.session_state.messages.append({
                    "role": "assistant", "content": thinking_after_prev_answer, "type": "thinking"
                })
            
            # This prepares the *next* question and its preceding thinking prompt.
            # It also updates question_index for the *next* cycle and current_question_id_for_next_prompt.
            thinking_before_next_q, next_q_text_content = get_next_question_and_thinking()
            
            # This sets current_question_id to the ID of the question that is about to be asked (or None if done/halted)
            st.session_state.current_question_id = st.session_state.get("current_question_id_for_next_prompt")
            
            if thinking_before_next_q: 
                st.session_state.messages.append({
                    "role": "assistant", "content": thinking_before_next_q, "type": "thinking"
                })
            
            if next_q_text_content: 
                msg_type = "question" # Default type
                if st.session_state.get("consultation_halted_due_to_risk", False):
                    msg_type = "alert" 
                # Check if it's the completion message (all questions done AND not halted)
                elif st.session_state.question_index > len(HARDCODED_QUESTIONS_AND_UPDATES) and \
                     not st.session_state.current_question_id and \
                     not st.session_state.get("consultation_halted_due_to_risk", False):
                    msg_type = "completion" 
                
                st.session_state.messages.append({
                    "role": "assistant", "content": next_q_text_content, "type": msg_type
                })
            
            st.rerun()

with col2:
    st.subheader("🗺️ Live Health Pathway Visualizer") 
    zc1, zc2, zc3 = st.columns(3)
    if zc1.button("Zoom In ➕",use_container_width=True, key="zoom_in"): st.session_state.zoom_level=max(0.1,st.session_state.zoom_level*0.8); st.rerun()
    if zc2.button("Zoom Out ➖",use_container_width=True, key="zoom_out"): st.session_state.zoom_level=min(10.0,st.session_state.zoom_level*1.25); st.rerun()
    if zc3.button("Reset View 🔎",use_container_width=True, key="reset_view"): 
        st.session_state.zoom_level=1.0; st.session_state.view_center_x=st.session_state.graph_content_center_x
        st.session_state.view_center_y=st.session_state.graph_content_center_y; st.session_state.view_initialized_by_data=False; st.rerun()
    pc1, pc2, pc3, pc4 = st.columns(4)
    PAN_F = 0.15 
    if pc1.button("← Pan Left",use_container_width=True, key="pan_left"): step=st.session_state.graph_extent_width*st.session_state.zoom_level*PAN_F; st.session_state.view_center_x-=step; st.rerun()
    if pc2.button("Pan Right →",use_container_width=True, key="pan_right"): step=st.session_state.graph_extent_width*st.session_state.zoom_level*PAN_F; st.session_state.view_center_x+=step; st.rerun()
    if pc3.button("↑ Pan Up",use_container_width=True, key="pan_up"): step=st.session_state.graph_extent_height*st.session_state.zoom_level*PAN_F; st.session_state.view_center_y+=step; st.rerun()
    if pc4.button("↓ Pan Down",use_container_width=True, key="pan_down"): step=st.session_state.graph_extent_height*st.session_state.zoom_level*PAN_F; st.session_state.view_center_y-=step; st.rerun()
    
    st.markdown("---")
    graph_display_container=st.container(key="graph_container_main")
    display_knowledge_graph(graph_display_container)

# Initialize conversation on first load
if not st.session_state.messages:
    thinking_before_first_q, first_q_text = get_next_question_and_thinking()
    st.session_state.current_question_id = st.session_state.get("current_question_id_for_next_prompt") 
    
    if thinking_before_first_q:
        st.session_state.messages.append({
            "role": "assistant", "content": thinking_before_first_q, "type": "thinking"
        })
    if first_q_text:
        st.session_state.messages.append({
            "role": "assistant", "content": first_q_text, "type": "question"
        })
    st.rerun()
