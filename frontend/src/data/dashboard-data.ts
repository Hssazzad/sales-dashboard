import type { AnalyticsBentoProps } from "@/components/ui/analytics-bento";

export type DashboardData = Pick<
  AnalyticsBentoProps,
  "revenue" | "sessions" | "categories" | "seasonality"
>;

export const dashboardMeta = {
  "source": "print_db",
  "generatedAt": "2026-10-26T21:26:10",
  "dataRange": {
    "from": "2025-08-02",
    "to": "2026-10-25"
  },
  "totalRevenue": 399068134,
  "totalRows": 101328,
  "totalOrders": 14683,
  "currency": "৳"
} as const;

export const dashboardData: DashboardData = {
  "revenue": {
    "label": "Revenue",
    "value": 37302165,
    "delta": "49.3%",
    "note": "Avg. order ৳41,036",
    "caption": "Last 30 days · Sep 26 – Oct 25",
    "series": [
      {
        "label": "Sep 26",
        "value": 565815
      },
      {
        "label": "Sep 27",
        "value": 1244945
      },
      {
        "label": "Sep 28",
        "value": 799835
      },
      {
        "label": "Sep 29",
        "value": 865985
      },
      {
        "label": "Sep 30",
        "value": 872780
      },
      {
        "label": "Oct 1",
        "value": 1048040
      },
      {
        "label": "Oct 2",
        "value": 0
      },
      {
        "label": "Oct 3",
        "value": 367050
      },
      {
        "label": "Oct 4",
        "value": 1391020
      },
      {
        "label": "Oct 5",
        "value": 7275580
      },
      {
        "label": "Oct 6",
        "value": 872295
      },
      {
        "label": "Oct 7",
        "value": 687190
      },
      {
        "label": "Oct 8",
        "value": 1670265
      },
      {
        "label": "Oct 9",
        "value": 0
      },
      {
        "label": "Oct 10",
        "value": 1986880
      },
      {
        "label": "Oct 11",
        "value": 1526300
      },
      {
        "label": "Oct 12",
        "value": 785370
      },
      {
        "label": "Oct 13",
        "value": 546040
      },
      {
        "label": "Oct 14",
        "value": 713875
      },
      {
        "label": "Oct 15",
        "value": 5168070
      },
      {
        "label": "Oct 16",
        "value": 0
      },
      {
        "label": "Oct 17",
        "value": 1310370
      },
      {
        "label": "Oct 18",
        "value": 2844130
      },
      {
        "label": "Oct 19",
        "value": 1247055
      },
      {
        "label": "Oct 20",
        "value": 831955
      },
      {
        "label": "Oct 21",
        "value": 141550
      },
      {
        "label": "Oct 22",
        "value": 0
      },
      {
        "label": "Oct 23",
        "value": 0
      },
      {
        "label": "Oct 24",
        "value": 1001170
      },
      {
        "label": "Oct 25",
        "value": 1538600
      }
    ]
  },
  "sessions": {
    "label": "Units sold",
    "value": 53405,
    "delta": "-22.6%",
    "note": "By hour, last 3 weeks",
    "desktop": [
      [
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        48,
        35,
        69,
        17,
        61,
        144,
        32,
        46,
        8,
        0,
        0,
        0,
        0,
        0
      ],
      [
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        258,
        113,
        135,
        42,
        181,
        138,
        68,
        82,
        35,
        1,
        0,
        0,
        0,
        0
      ],
      [
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        172,
        116,
        144,
        47,
        108,
        133,
        107,
        95,
        28,
        0,
        0,
        0,
        0,
        0
      ]
    ],
    "mobile": [
      [
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        2,
        1,
        5,
        2,
        7,
        8,
        1,
        4,
        2,
        0,
        0,
        0,
        0,
        0
      ],
      [
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        5,
        6,
        1,
        8,
        8,
        11,
        9,
        8,
        0,
        0,
        0,
        0,
        0
      ],
      [
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        3,
        3,
        10,
        2,
        4,
        11,
        3,
        6,
        2,
        0,
        0,
        0,
        0,
        0
      ]
    ],
    "labels": {
      "desktop": "Main store",
      "mobile": "Showroom",
      "prior": "Prior weeks",
      "current": "this week"
    }
  },
  "categories": {
    "title": "Top product groups",
    "groups": [
      {
        "id": "consumables",
        "name": "Consumables",
        "color": "#7CFF5B",
        "ink": "dark"
      },
      {
        "id": "hardware",
        "name": "Hardware",
        "color": "#8B3DFF",
        "ink": "light"
      }
    ],
    "periods": [
      {
        "label": "Weekly",
        "total": 4694630,
        "delta": "-55.8%",
        "compare": "vs ৳10,611,055 prior week"
      },
      {
        "label": "Monthly",
        "total": 35842015,
        "delta": "53.7%",
        "compare": "vs ৳23,320,339 prior month"
      },
      {
        "label": "Yearly",
        "total": 325246720,
        "delta": "n/a",
        "compare": "vs ৳45,541,979 · only 85 days of data"
      }
    ],
    "items": [
      {
        "name": "Laser Printer",
        "group": "hardware",
        "values": [
          238000,
          13741500,
          36011400
        ]
      },
      {
        "name": "Inkjet Printer",
        "group": "hardware",
        "values": [
          2885000,
          9204800,
          101093900
        ]
      },
      {
        "name": "Toner",
        "group": "consumables",
        "values": [
          805265,
          8624165,
          133335385
        ]
      },
      {
        "name": "Ink",
        "group": "consumables",
        "values": [
          438500,
          2075380,
          31033176
        ]
      },
      {
        "name": "Photo Paper",
        "group": "consumables",
        "values": [
          154615,
          1598470,
          20250434
        ]
      },
      {
        "name": "Ink Cartridge",
        "group": "consumables",
        "values": [
          173250,
          597700,
          3522425
        ]
      }
    ],
    "table": {
      "columns": [
        "Brand",
        "Weekly",
        "Monthly",
        "Yearly"
      ],
      "rows": [
        {
          "label": "CANON",
          "values": [
            "৳776,250",
            "৳9,903,650",
            "৳67,121,285"
          ]
        },
        {
          "label": "HP",
          "values": [
            "৳194,720",
            "৳8,593,990",
            "৳19,083,850"
          ]
        },
        {
          "label": "EPSON",
          "values": [
            "৳2,450,400",
            "৳6,187,600",
            "৳69,312,435"
          ]
        }
      ]
    }
  },
  "seasonality": {
    "title": "Seasonality",
    "axis": [
      "Nov",
      "Dec",
      "Jan",
      "Feb",
      "Mar",
      "Apr",
      "May",
      "Jun",
      "Jul",
      "Aug",
      "Sep",
      "Oct"
    ],
    "years": [
      {
        "label": "2025-26",
        "values": [
          26464576,
          24988223,
          32495884,
          21709394,
          16231595,
          30751566,
          20105319,
          32694907,
          40765752,
          41144525,
          23229669,
          32952805
        ],
        "stats": [
          {
            "label": "Monthly avg",
            "value": 28627851,
            "delta": "76.4%",
            "note": "vs Mar 2026 low"
          },
          {
            "label": "Best month",
            "value": 41144525,
            "delta": "43.7%",
            "note": "Aug 2026 · vs avg"
          }
        ],
        "rows": [
          {
            "label": "PRINTEX",
            "value": "94,237,660"
          },
          {
            "label": "EPSON",
            "value": "68,947,180"
          },
          {
            "label": "CANON",
            "value": "67,110,685"
          }
        ]
      }
    ]
  }
};
