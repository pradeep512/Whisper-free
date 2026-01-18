use dynisland_macro::{MultiWidgetConfig, OptDeserializeConfig};
use serde::{Deserialize, Serialize};

#[derive(Clone, PartialEq, Serialize, MultiWidgetConfig, OptDeserializeConfig, Debug)]
pub struct TestConfig {
    #[serde(skip_serializing)]
    pub(crate) scrolling: bool,
    #[serde(skip_serializing)]
    pub(crate) scrolling_speed: f32,
    #[serde(skip_serializing)]
    pub max_width: i32,
    #[serde(skip_serializing)]
    pub(crate) minimal_image: String,
    #[child_only]
    pub(crate) exec: String,
    #[serde(skip_serializing)]
    #[deserialize_struct(DeWinPos)]
    pub(crate) win_pos: WinPos,
}
impl Default for TestConfig {
    fn default() -> Self {
        Self {
            scrolling: true,
            scrolling_speed: 30.0,
            max_width: 300,
            minimal_image: "image-missing-symbolic".to_string(),
            exec: "test".to_string(),
            win_pos: WinPos::default(),
        }
    }
}

#[derive(Clone, PartialEq, Serialize, MultiWidgetConfig, OptDeserializeConfig, Debug, Default)]
pub struct Empty {}

#[derive(Debug, PartialEq, Clone, Default, Deserialize, Serialize, OptDeserializeConfig)]
pub struct WinPos {
    pub(crate) layer: u64,
}

#[test]
fn test_multi_widget_config_derive() {
    let test = TestConfig::default();
    let test_opt = DeTestConfigMain::default();
    let test_main = test_opt.into_main_config();
    assert_eq!(test, test_main.get_for_window("test", 0));
}

#[test]
fn test_parse_serde_empty() {
    let test = TestConfig::default();
    let test_opt: DeTestConfigMain = serde_json::from_str("{}").unwrap();
    let test_main = test_opt.into_main_config();
    assert_eq!(test, test_main.get_for_window("window", 0));
}

#[test]
fn test_parse_serde_full() {
    let test = TestConfig {
        scrolling: false,
        scrolling_speed: 40.0,
        max_width: 3000,
        minimal_image: "image-missing-symbolic1".to_string(),
        exec: "echo test".to_string(),
        win_pos: WinPos { layer: 0 },
    };
    let test1 = TestConfig {
        scrolling: true,
        scrolling_speed: 32.0,
        max_width: 300,
        minimal_image: "image-missing-symbolic1".to_string(),
        exec: "test".to_string(),
        win_pos: WinPos { layer: 0 },
    };
    let test_opt: DeTestConfigMain = serde_json::from_str(
        r#"{
        "scrolling": true,
        "scrolling_speed": 32.0,
        "max_width": 300,
        "minimal_image": "image-missing-symbolic1",
        "win_pos": {
            "layer": 0
        },
        "windows": {
            "window": [
                {
                    "scrolling": false,
                    "scrolling_speed": 40.0,
                    "max_width": 3000,
                    "minimal_image": "image-missing-symbolic1",
                    "win_pos": {
                        "layer": 0
                    },
                    "exec": "echo test"
                }
            ],
            "window2": [
            ]
        }
    }"#,
    )
    .unwrap();
    let test_main = test_opt.into_main_config();
    assert_eq!(test, test_main.get_for_window("window", 0));
    assert_eq!(test1, test_main.get_for_window("window2", 0));
}

#[test]
fn test_serialize_default() {
    let mut conf = TestConfigMain::default();
    conf.windows
        .insert("".to_string(), vec![TestConfig::default()]);
    let expected = r#"{"scrolling":true,"scrolling_speed":30.0,"max_width":300,"minimal_image":"image-missing-symbolic","win_pos":{"layer":0},"windows":{"":[{"exec":"test"}]}}"#;
    assert_eq!(expected, serde_json::to_string(&conf).unwrap());
}
